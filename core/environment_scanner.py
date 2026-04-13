"""
환경 스캐너 모듈

시스템 환경을 스캔하고 Python 경로, 필수 패키지 등을 확인합니다.
컴퓨터별 환경 설정을 저장하고 로드하여 중복 스캔을 방지합니다.
"""

import sys
import os
import json
import subprocess
import platform
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import uuid


class EnvironmentScanner:
    """시스템 환경 스캐너"""

    # 필수 패키지 목록 (패키지명, import명)
    _COMMON_PACKAGES = [
        ("PyQt6", "PyQt6"),
        ("pyautogui", "pyautogui"),
        ("Pillow", "PIL"),
        ("mss", "mss"),
    ]
    _WINDOWS_ONLY_PACKAGES = [
        ("pywinauto", "pywinauto"),
        ("pywin32", "win32api"),
    ]
    REQUIRED_PACKAGES = (
        _COMMON_PACKAGES + _WINDOWS_ONLY_PACKAGES
        if sys.platform == "win32"
        else _COMMON_PACKAGES
    )

    # 선택적 패키지 (없어도 실행 가능)
    OPTIONAL_PACKAGES = [
        ("selenium", "selenium"),
        ("playwright", "playwright"),
    ]

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Args:
            config_dir: 환경 설정 저장 디렉토리 (기본: 프로젝트/config/)
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"

        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.env_file = self.config_dir / "environment.json"

        self._cached_env: Optional[Dict] = None

    def get_machine_id(self) -> str:
        """현재 컴퓨터의 고유 식별자 생성"""
        # 여러 시스템 정보를 조합하여 해시 생성
        info_parts = [
            platform.node(),  # 호스트명
            platform.machine(),  # CPU 아키텍처
            platform.processor(),  # 프로세서 정보
        ]

        # MAC 주소 추가 (가능한 경우)
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
                          for ele in range(0, 48, 8)][::-1])
            info_parts.append(mac)
        except:
            pass

        # 사용자 이름 추가
        info_parts.append(os.environ.get('USERNAME', os.environ.get('USER', '')))

        combined = '|'.join(info_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def load_saved_environment(self) -> Optional[Dict]:
        """저장된 환경 설정 로드"""
        if not self.env_file.exists():
            return None

        try:
            with open(self.env_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 현재 컴퓨터의 환경인지 확인
            saved_machine_id = data.get('machine_id')
            current_machine_id = self.get_machine_id()

            if saved_machine_id == current_machine_id:
                # 추가 검증: Python 경로가 존재하는지 확인
                python_path = data.get('python_path')
                if python_path and os.path.exists(python_path):
                    return data
                else:
                    # Python 경로가 없으면 환경 파일 삭제
                    print(f"[WARNING] 저장된 Python 경로가 존재하지 않습니다: {python_path}")
                    self._delete_environment_file()
                    return None
            else:
                # 다른 컴퓨터의 환경 - 파일 삭제 후 새로 스캔 필요
                saved_hostname = data.get('hostname', 'unknown')
                print(f"[INFO] 다른 컴퓨터의 환경 설정 감지 (호스트: {saved_hostname}). 환경 파일을 삭제하고 새로 스캔합니다.")
                self._delete_environment_file()
                return None

        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARNING] 환경 파일 읽기 오류: {e}")
            self._delete_environment_file()
            return None

    def _delete_environment_file(self):
        """환경 설정 파일 삭제"""
        try:
            if self.env_file.exists():
                self.env_file.unlink()
                print(f"[INFO] 환경 설정 파일 삭제됨: {self.env_file}")
        except Exception as e:
            print(f"[WARNING] 환경 파일 삭제 실패: {e}")

    def save_environment(self, env_data: Dict) -> bool:
        """환경 설정 저장"""
        try:
            env_data['machine_id'] = self.get_machine_id()
            env_data['last_scan'] = datetime.now().isoformat()
            env_data['hostname'] = platform.node()

            with open(self.env_file, 'w', encoding='utf-8') as f:
                json.dump(env_data, f, ensure_ascii=False, indent=2)

            self._cached_env = env_data
            return True
        except IOError:
            return False

    def find_python_paths(self) -> List[Dict]:
        """시스템에서 사용 가능한 Python 경로 탐색"""
        python_paths = []

        # 1. 현재 실행 중인 Python
        current_python = {
            'path': sys.executable,
            'version': platform.python_version(),
            'is_current': True,
            'is_venv': hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix),
            'exists': os.path.exists(sys.executable)
        }
        python_paths.append(current_python)

        # 2. PATH에서 python 검색
        for name in ['python', 'python3', 'py']:
            path = shutil.which(name)
            if path and path != sys.executable and os.path.exists(path):
                try:
                    result = subprocess.run(
                        [path, '--version'],
                        capture_output=True, text=True, timeout=5
                    )
                    version = result.stdout.strip().replace('Python ', '')
                except:
                    version = "unknown"

                python_paths.append({
                    'path': path,
                    'version': version,
                    'is_current': False,
                    'is_venv': False,
                    'exists': True
                })

        # 3. 일반적인 설치 위치 검색 (Windows)
        common_locations = [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Python',
            Path('C:/Python'),
            Path('C:/Program Files/Python'),
            Path(os.environ.get('USERPROFILE', '')) / 'AppData' / 'Local' / 'Programs' / 'Python',
        ]

        for base_path in common_locations:
            if base_path.exists():
                for subdir in base_path.iterdir():
                    if subdir.is_dir():
                        python_exe = subdir / 'python.exe'
                        if python_exe.exists() and str(python_exe) not in [p['path'] for p in python_paths]:
                            try:
                                result = subprocess.run(
                                    [str(python_exe), '--version'],
                                    capture_output=True, text=True, timeout=5
                                )
                                version = result.stdout.strip().replace('Python ', '')
                            except:
                                version = "unknown"

                            python_paths.append({
                                'path': str(python_exe),
                                'version': version,
                                'is_current': False,
                                'is_venv': False,
                                'exists': True
                            })

        # 4. 프로젝트 내 venv 검색
        project_root = Path(__file__).parent.parent
        venv_python = project_root / 'venv' / 'Scripts' / 'python.exe'
        if venv_python.exists() and str(venv_python) not in [p['path'] for p in python_paths]:
            try:
                result = subprocess.run(
                    [str(venv_python), '--version'],
                    capture_output=True, text=True, timeout=5
                )
                version = result.stdout.strip().replace('Python ', '')
            except:
                version = "unknown"

            python_paths.append({
                'path': str(venv_python),
                'version': version,
                'is_current': False,
                'is_venv': True,
                'exists': True
            })

        return python_paths

    def check_package(self, python_path: str, package_name: str, import_name: str) -> Dict:
        """특정 Python 경로에서 패키지 설치 여부 확인"""
        try:
            result = subprocess.run(
                [python_path, '-c', f'import {import_name}; print("OK")'],
                capture_output=True, text=True, timeout=10
            )
            installed = result.returncode == 0 and 'OK' in result.stdout

            # 버전 확인 시도
            version = None
            if installed:
                try:
                    ver_result = subprocess.run(
                        [python_path, '-c', f'import {import_name}; print(getattr({import_name}, "__version__", "unknown"))'],
                        capture_output=True, text=True, timeout=10
                    )
                    version = ver_result.stdout.strip()
                except:
                    pass

            return {
                'package': package_name,
                'import_name': import_name,
                'installed': installed,
                'version': version,
                'error': None
            }

        except subprocess.TimeoutExpired:
            return {
                'package': package_name,
                'import_name': import_name,
                'installed': False,
                'version': None,
                'error': 'timeout'
            }
        except Exception as e:
            return {
                'package': package_name,
                'import_name': import_name,
                'installed': False,
                'version': None,
                'error': str(e)
            }

    def check_all_packages(self, python_path: str) -> Dict[str, List[Dict]]:
        """모든 필수/선택 패키지 상태 확인"""
        results = {
            'required': [],
            'optional': [],
            'all_required_installed': True
        }

        for pkg, imp in self.REQUIRED_PACKAGES:
            status = self.check_package(python_path, pkg, imp)
            results['required'].append(status)
            if not status['installed']:
                results['all_required_installed'] = False

        for pkg, imp in self.OPTIONAL_PACKAGES:
            status = self.check_package(python_path, pkg, imp)
            results['optional'].append(status)

        return results

    def get_system_info(self) -> Dict:
        """시스템 정보 수집"""
        return {
            'os': platform.system(),
            'os_version': platform.version(),
            'os_release': platform.release(),
            'architecture': platform.machine(),
            'processor': platform.processor(),
            'hostname': platform.node(),
            'username': os.environ.get('USERNAME', os.environ.get('USER', 'unknown')),
            'python_version': platform.python_version(),
        }

    def full_scan(self, python_path: Optional[str] = None) -> Dict:
        """전체 환경 스캔 수행"""
        if python_path is None:
            python_path = sys.executable

        # Python 경로 유효성 확인
        if not os.path.exists(python_path):
            return {
                'success': False,
                'error': f'Python 경로를 찾을 수 없습니다: {python_path}',
                'python_path': python_path
            }

        env_data = {
            'success': True,
            'machine_id': self.get_machine_id(),
            'system_info': self.get_system_info(),
            'python_path': python_path,
            'python_version': None,
            'available_pythons': self.find_python_paths(),
            'packages': None,
            'scan_time': datetime.now().isoformat()
        }

        # Python 버전 확인
        try:
            result = subprocess.run(
                [python_path, '--version'],
                capture_output=True, text=True, timeout=5
            )
            env_data['python_version'] = result.stdout.strip().replace('Python ', '')
        except:
            env_data['python_version'] = 'unknown'

        # 패키지 상태 확인
        env_data['packages'] = self.check_all_packages(python_path)

        return env_data

    def is_environment_valid(self, saved_env: Optional[Dict] = None) -> Tuple[bool, str]:
        """저장된 환경이 유효한지 확인"""
        if saved_env is None:
            saved_env = self.load_saved_environment()

        if saved_env is None:
            return False, "저장된 환경 설정이 없습니다."

        # Python 경로 존재 확인
        python_path = saved_env.get('python_path')
        if not python_path or not os.path.exists(python_path):
            return False, f"Python 경로를 찾을 수 없습니다: {python_path}"

        # 머신 ID 확인
        if saved_env.get('machine_id') != self.get_machine_id():
            return False, "다른 컴퓨터의 환경 설정입니다."

        # 패키지 상태 확인 (캐시된 정보 사용 - 빠른 체크)
        packages = saved_env.get('packages', {})
        if not packages.get('all_required_installed', False):
            return False, "일부 필수 패키지가 설치되어 있지 않습니다."

        return True, "환경이 유효합니다."

    def install_package(self, python_path: str, package_name: str) -> Tuple[bool, str]:
        """패키지 설치"""
        try:
            result = subprocess.run(
                [python_path, '-m', 'pip', 'install', package_name],
                capture_output=True, text=True, timeout=300
            )

            if result.returncode == 0:
                return True, f"{package_name} 설치 완료"
            else:
                return False, result.stderr

        except subprocess.TimeoutExpired:
            return False, "설치 시간 초과"
        except Exception as e:
            return False, str(e)

    def install_missing_packages(self, python_path: str, packages: List[Dict]) -> List[Dict]:
        """누락된 패키지 설치"""
        results = []

        for pkg in packages:
            if not pkg.get('installed'):
                success, message = self.install_package(python_path, pkg['package'])
                results.append({
                    'package': pkg['package'],
                    'success': success,
                    'message': message
                })

        return results


def get_scanner() -> EnvironmentScanner:
    """환경 스캐너 싱글톤 인스턴스 반환"""
    if not hasattr(get_scanner, '_instance'):
        get_scanner._instance = EnvironmentScanner()
    return get_scanner._instance

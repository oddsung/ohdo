# SPDX-License-Identifier: AGPL-3.0-or-later
"""
환경 스캐너 모듈

시스템 환경을 스캔하고 Python 경로, 필수 패키지 등을 확인합니다.
컴퓨터별 환경 설정을 저장하고 로드하여 중복 스캔을 방지합니다.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class EnvironmentScanner:
    """시스템 환경 스캐너"""

    # 필수 패키지 목록 (패키지명, import명)
    _COMMON_PACKAGES = [
        ("PySide6", "PySide6"),
        ("pyautogui", "pyautogui"),
        ("Pillow", "PIL"),
        ("mss", "mss"),
    ]
    _WINDOWS_ONLY_PACKAGES = [
        ("pywinauto", "pywinauto"),
        ("pywin32", "win32api"),
    ]
    REQUIRED_PACKAGES = (
        _COMMON_PACKAGES + _WINDOWS_ONLY_PACKAGES if sys.platform == "win32" else _COMMON_PACKAGES
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
            mac = ":".join(
                ["{:02x}".format((uuid.getnode() >> ele) & 0xFF) for ele in range(0, 48, 8)][::-1]
            )
            info_parts.append(mac)
        except Exception as e:
            # uuid.getnode() 가 매우 드물게 실패할 수 있음 — 호스트명/CPU 만으로도 ID 안정적
            print(f"[DEBUG] MAC 주소 수집 실패 (무시됨): {e}")

        # 사용자 이름 추가
        info_parts.append(os.environ.get("USERNAME", os.environ.get("USER", "")))

        combined = "|".join(info_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def load_saved_environment(self) -> Optional[Dict]:
        """저장된 환경 설정 로드"""
        if not self.env_file.exists():
            return None

        try:
            with open(self.env_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 현재 컴퓨터의 환경인지 확인
            saved_machine_id = data.get("machine_id")
            current_machine_id = self.get_machine_id()

            if saved_machine_id == current_machine_id:
                # 추가 검증: Python 경로가 존재하는지 확인
                python_path = data.get("python_path")
                if python_path and os.path.exists(python_path):
                    return data
                else:
                    # Python 경로가 없으면 환경 파일 삭제
                    print(f"[WARNING] 저장된 Python 경로가 존재하지 않습니다: {python_path}")
                    self._delete_environment_file()
                    return None
            else:
                # 다른 컴퓨터의 환경 - 파일 삭제 후 새로 스캔 필요
                saved_hostname = data.get("hostname", "unknown")
                print(
                    f"[INFO] 다른 컴퓨터의 환경 설정 감지 (호스트: {saved_hostname}). 환경 파일을 삭제하고 새로 스캔합니다."
                )
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
            env_data["machine_id"] = self.get_machine_id()
            env_data["last_scan"] = datetime.now().isoformat()
            env_data["hostname"] = platform.node()

            with open(self.env_file, "w", encoding="utf-8") as f:
                json.dump(env_data, f, ensure_ascii=False, indent=2)

            self._cached_env = env_data
            return True
        except IOError:
            return False

    @staticmethod
    def _probe_python_version(python_path: str, timeout: int = 5) -> str:
        """주어진 python.exe 의 버전 문자열을 안전하게 조회.

        실패 사유는 silent 가 아니라 좁혀서 처리한다 — 예상 가능한 실패
        (subprocess/OSError) 만 'unknown' 으로 폴백하고, 그 외 예외는 위로
        전파시켜 디버깅을 어렵게 만들지 않는다.
        """
        try:
            result = subprocess.run(
                [python_path, "--version"], capture_output=True, text=True, timeout=timeout
            )
            return result.stdout.strip().replace("Python ", "") or "unknown"
        except (subprocess.SubprocessError, OSError, UnicodeDecodeError) as e:
            print(f"[DEBUG] Python 버전 조회 실패 ({python_path}): {e}")
            return "unknown"

    def check_cli_ai(self, command: str = "agy", timeout: int = 10) -> Dict:
        """[handoff §36 2026-05-24] CLI AI 도구가 설치되어 있고 실행 가능한지 검증.

        이전 ``check_gemini_cli`` 의 일반화 버전. agy / claude / codex 등 어떤
        CLI AI 든 ``<command> --version`` 으로 검증. ``check_gemini_cli`` 는
        back-compat alias 로 유지.

        반환 dict 키:
            - installed: PATH 에서 찾았고 --version 호출이 성공한 경우 True
            - command: 검사한 명령어 (기본 'agy')
            - path: shutil.which 결과 (없으면 None)
            - version: '<command> --version' 의 stdout (실패 시 None)
            - error: 'not_found' | 'timeout' | 'non_zero_exit' | None
            - detail: 사람이 읽을 수 있는 추가 메시지 (옵션)
        """
        result: Dict = {
            "installed": False,
            "command": command,
            "path": None,
            "version": None,
            "error": None,
            "detail": None,
        }

        path = shutil.which(command)
        if not path:
            result["error"] = "not_found"
            result["detail"] = f"PATH 에서 '{command}' 를 찾을 수 없습니다."
            return result

        result["path"] = path

        try:
            proc = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            result["error"] = "timeout"
            result["detail"] = f"'{command} --version' 이 {timeout}초 안에 응답하지 않았습니다."
            return result
        except (OSError, UnicodeDecodeError) as e:
            result["error"] = "execution_error"
            result["detail"] = f"실행 중 오류: {e}"
            return result

        if proc.returncode != 0:
            result["error"] = "non_zero_exit"
            stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
            result["detail"] = f"종료 코드 {proc.returncode}: {stderr_tail[0]}"
            return result

        version = (proc.stdout or proc.stderr or "").strip()
        result["installed"] = True
        result["version"] = version or "unknown"
        return result

    # 2026-05-24 (handoff §36): back-compat alias — 기존 호출자 ``check_gemini_cli``
    # 가 그대로 동작. default command 만 새 이름 'agy' 로 변경 (Google rename).
    check_gemini_cli = check_cli_ai

    def find_python_paths(self) -> List[Dict]:
        """시스템에서 사용 가능한 Python 경로 탐색"""
        python_paths = []

        # 1. 현재 실행 중인 Python
        current_python = {
            "path": sys.executable,
            "version": platform.python_version(),
            "is_current": True,
            "is_venv": hasattr(sys, "real_prefix")
            or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix),
            "exists": os.path.exists(sys.executable),
        }
        python_paths.append(current_python)

        # 2. PATH에서 python 검색
        for name in ["python", "python3", "py"]:
            path = shutil.which(name)
            if path and path != sys.executable and os.path.exists(path):
                python_paths.append(
                    {
                        "path": path,
                        "version": self._probe_python_version(path),
                        "is_current": False,
                        "is_venv": False,
                        "exists": True,
                    }
                )

        # 3. 일반적인 설치 위치 검색 (Windows)
        common_locations = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path("C:/Python"),
            Path("C:/Program Files/Python"),
            Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Programs" / "Python",
        ]

        for base_path in common_locations:
            if base_path.exists():
                for subdir in base_path.iterdir():
                    if subdir.is_dir():
                        python_exe = subdir / "python.exe"
                        if python_exe.exists() and str(python_exe) not in [
                            p["path"] for p in python_paths
                        ]:
                            python_paths.append(
                                {
                                    "path": str(python_exe),
                                    "version": self._probe_python_version(str(python_exe)),
                                    "is_current": False,
                                    "is_venv": False,
                                    "exists": True,
                                }
                            )

        # 4. 프로젝트 내 venv 검색
        project_root = Path(__file__).parent.parent
        venv_python = project_root / "venv" / "Scripts" / "python.exe"
        if venv_python.exists() and str(venv_python) not in [p["path"] for p in python_paths]:
            python_paths.append(
                {
                    "path": str(venv_python),
                    "version": self._probe_python_version(str(venv_python)),
                    "is_current": False,
                    "is_venv": True,
                    "exists": True,
                }
            )

        return python_paths

    def check_package(self, python_path: str, package_name: str, import_name: str) -> Dict:
        """특정 Python 경로에서 패키지 설치 여부 확인"""
        try:
            result = subprocess.run(
                [python_path, "-c", f'import {import_name}; print("OK")'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            installed = result.returncode == 0 and "OK" in result.stdout

            # 버전 확인 시도
            version = None
            if installed:
                try:
                    ver_result = subprocess.run(
                        [
                            python_path,
                            "-c",
                            f'import {import_name}; print(getattr({import_name}, "__version__", "unknown"))',
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    version = ver_result.stdout.strip()
                except (subprocess.SubprocessError, OSError, UnicodeDecodeError) as e:
                    # 패키지는 import 됐는데 __version__ 만 못 읽는 경우 — 로그만 남기고 None
                    print(f"[DEBUG] {package_name} 버전 조회 실패 (무시됨): {e}")

            return {
                "package": package_name,
                "import_name": import_name,
                "installed": installed,
                "version": version,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            return {
                "package": package_name,
                "import_name": import_name,
                "installed": False,
                "version": None,
                "error": "timeout",
            }
        except Exception as e:
            return {
                "package": package_name,
                "import_name": import_name,
                "installed": False,
                "version": None,
                "error": str(e),
            }

    def check_all_packages(self, python_path: str) -> Dict[str, List[Dict]]:
        """모든 필수/선택 패키지 상태 확인"""
        results = {"required": [], "optional": [], "all_required_installed": True}

        for pkg, imp in self.REQUIRED_PACKAGES:
            status = self.check_package(python_path, pkg, imp)
            results["required"].append(status)
            if not status["installed"]:
                results["all_required_installed"] = False

        for pkg, imp in self.OPTIONAL_PACKAGES:
            status = self.check_package(python_path, pkg, imp)
            results["optional"].append(status)

        return results

    def get_system_info(self) -> Dict:
        """시스템 정보 수집"""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "username": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
            "python_version": platform.python_version(),
        }

    def full_scan(self, python_path: Optional[str] = None) -> Dict:
        """전체 환경 스캔 수행"""
        if python_path is None:
            python_path = sys.executable

        # Python 경로 유효성 확인
        if not os.path.exists(python_path):
            return {
                "success": False,
                "error": f"Python 경로를 찾을 수 없습니다: {python_path}",
                "python_path": python_path,
            }

        env_data = {
            "success": True,
            "machine_id": self.get_machine_id(),
            "system_info": self.get_system_info(),
            "python_path": python_path,
            "python_version": self._probe_python_version(python_path),
            "available_pythons": self.find_python_paths(),
            "packages": None,
            "cli_ai": None,
            "gemini_cli": None,  # back-compat alias (handoff §36) — 동일 값 가리킴
            "scan_time": datetime.now().isoformat(),
        }

        # 패키지 상태 확인
        env_data["packages"] = self.check_all_packages(python_path)

        # CLI AI 검사 — 미설치여도 앱은 기동 가능 (UI 만 동작), 따라서
        # full_scan 결과에는 포함하되 is_environment_valid 의 invalid 사유에는
        # 포함하지 않는다. dialog 가 별도로 게이트한다.
        # 2026-05-24 (handoff §36): "gemini" → "agy" rename, "cli_ai" 키 신규.
        # 기존 호출자 호환 위해 "gemini_cli" 키에도 같은 값 alias.
        cli_status = self.check_cli_ai()
        env_data["cli_ai"] = cli_status
        env_data["gemini_cli"] = cli_status

        return env_data

    def is_environment_valid(self, saved_env: Optional[Dict] = None) -> Tuple[bool, str]:
        """저장된 환경이 유효한지 확인"""
        if saved_env is None:
            saved_env = self.load_saved_environment()

        if saved_env is None:
            return False, "저장된 환경 설정이 없습니다."

        # Python 경로 존재 확인
        python_path = saved_env.get("python_path")
        if not python_path or not os.path.exists(python_path):
            return False, f"Python 경로를 찾을 수 없습니다: {python_path}"

        # 머신 ID 확인
        if saved_env.get("machine_id") != self.get_machine_id():
            return False, "다른 컴퓨터의 환경 설정입니다."

        # 패키지 상태 확인 (캐시된 정보 사용 - 빠른 체크)
        packages = saved_env.get("packages", {})
        if not packages.get("all_required_installed", False):
            return False, "일부 필수 패키지가 설치되어 있지 않습니다."

        return True, "환경이 유효합니다."

    def install_package(self, python_path: str, package_name: str) -> Tuple[bool, str]:
        """패키지 설치"""
        try:
            result = subprocess.run(
                [python_path, "-m", "pip", "install", package_name],
                capture_output=True,
                text=True,
                timeout=300,
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
            if not pkg.get("installed"):
                success, message = self.install_package(python_path, pkg["package"])
                results.append({"package": pkg["package"], "success": success, "message": message})

        return results


def get_scanner() -> EnvironmentScanner:
    """환경 스캐너 싱글톤 인스턴스 반환"""
    if not hasattr(get_scanner, "_instance"):
        get_scanner._instance = EnvironmentScanner()
    return get_scanner._instance

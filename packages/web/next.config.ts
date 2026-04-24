import type { NextConfig } from "next";

// 백엔드 직접 호출 URL. 로컬 개발 기본 http://localhost:8000,
// 프로덕션 배포는 Railway Control Plane 주소.
const backend = process.env.API_BASE_URL ?? "http://localhost:8000";

const config: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      // REST API: 쿠키·CORS 고민 없이 same-origin 으로 쓰기 위한 proxy.
      { source: "/v0/:path*", destination: `${backend}/v0/:path*` },
      // 매직링크 verify 도 브라우저가 3000 으로 맞았을 때 302/쿠키가 3000 도메인에 붙도록
      // 같이 proxy. 사용자 입장에선 link 가 http://localhost:3000/auth/verify?token=... 로 뜸.
      { source: "/auth/verify", destination: `${backend}/auth/verify` },
    ];
  },
};

export default config;

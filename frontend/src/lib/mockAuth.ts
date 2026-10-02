/**
 * DEV-ONLY mock identities. Only ever reached when NEXT_PUBLIC_USE_MOCKS=true (the production build refuses to
 * start with that flag - see next.config.mjs). Imported dynamically so the normal code path never touches it.
 */
import { AuthTokens, AuthUser } from "@/types/auth";

export const MOCK_USERS: Record<string, { user: AuthUser; pass: string }> = {
  admin: {
    pass: "password123",
    user: {
      id: "usr-admin-01", username: "admin", email: "admin@sharonesl.com", first_name: "Sharon", last_name: "Admin",
      role: "admin", country: "ZA", timezone: "Africa/Johannesburg",
    },
  },
  student_aiko: {
    pass: "password123",
    user: {
      id: "usr-student-01", username: "student_aiko", email: "aiko.tanaka@tokyo-corp.jp", first_name: "Aiko",
      last_name: "Tanaka", role: "student", country: "JP", timezone: "Asia/Tokyo", credits: 6,
    },
  },
  teacher_sharon: {
    pass: "password123",
    user: {
      id: "usr-teacher-01", username: "teacher_sharon", email: "sharon.tutor@sharonesl.com", first_name: "Sharon",
      last_name: "M.", role: "teacher", country: "ZA", timezone: "Africa/Johannesburg", is_verified: true,
    },
  },
};

export function mockLogin(username: string, password: string): { tokens: AuthTokens; user: AuthUser } | null {
  const mock = MOCK_USERS[username];
  if (!mock || mock.pass !== password) return null;
  const stamp = Date.now();
  return {
    user: mock.user,
    tokens: { access: `mock_jwt_access_${mock.user.role}_${stamp}`, refresh: `mock_jwt_refresh_${mock.user.role}_${stamp}` },
  };
}

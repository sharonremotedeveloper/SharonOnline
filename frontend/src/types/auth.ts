import type { components } from "./api.generated";

export type UserRole = "student" | "teacher" | "admin";
export type TutorStatus = components["schemas"]["TutorStatusEnum"];

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  country: string;
  timezone: string;
  avatar_url?: string; // Tutors: profile photo; "" otherwise
  phone_number?: string;
  credits?: number | null; // Remaining lesson credits for students; null for other roles
  is_verified?: boolean | null; // Tutor vetting status; null for other roles
  tutor_status?: TutorStatus | null; // Tutor lifecycle (docs/TUTOR_STATUS_MACHINE.md); null for other roles (T1c)
  email_verified?: boolean; // The address has been confirmed via the e-mailed link
  created_at?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse {
  tokens: AuthTokens;
  user: AuthUser;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  country: string;
  timezone: string;
  phone_number?: string;
  // Tutor specific fields
  has_power_backup?: boolean;
  tefl_certified?: boolean;
}

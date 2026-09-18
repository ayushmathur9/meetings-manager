import { api } from "@/lib/api/client";
import type { User } from "@/types";

export const usersApi = {
  list: () => api.get<User[]>("/users"),
};

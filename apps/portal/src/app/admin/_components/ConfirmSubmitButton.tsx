"use client";
// 확인 다이얼로그와 pending 비활성화를 묶은 제출 버튼. server action form 안에서 쓴다.
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { Button, type ButtonVariant } from "./Button";

interface Props {
  message: string;
  variant?: ButtonVariant;
  pendingLabel?: string;
  children: ReactNode;
}

export function ConfirmSubmitButton({ message, variant = "secondary", pendingLabel = "처리 중…", children }: Props) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant={variant}
      disabled={pending}
      onClick={(e) => {
        if (!confirm(message)) e.preventDefault();
      }}
    >
      {pending ? pendingLabel : children}
    </Button>
  );
}

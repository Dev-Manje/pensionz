import TextField from "@mui/material/TextField";

export const PASSWORD_RULE = "At least 8 characters, with a letter and a number.";

// Same rule as the server (services/passwords.check_policy); returns why a
// new password isn't acceptable yet, or null.
export function newPasswordProblem(password: string, confirm: string): string | null {
  if (password.length < 8) return "Use at least 8 characters";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return "Include at least one letter and one number";
  if (confirm && confirm !== password) return "The two passwords don't match";
  return null;
}

// "New password" + "Confirm new password", with the rule shown up front and
// errors only once the user has typed something.
export function NewPasswordFields({
  password,
  confirm,
  onPassword,
  onConfirm,
  label = "New password",
}: {
  password: string;
  confirm: string;
  onPassword: (v: string) => void;
  onConfirm: (v: string) => void;
  label?: string;
}) {
  const problem = password ? newPasswordProblem(password, "") : null;
  const mismatch = confirm.length > 0 && confirm !== password;
  return (
    <>
      <TextField
        label={label}
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => onPassword(e.target.value)}
        error={!!problem}
        helperText={problem ?? PASSWORD_RULE}
        required
        fullWidth
      />
      <TextField
        label={`Confirm ${label.toLowerCase()}`}
        type="password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => onConfirm(e.target.value)}
        error={mismatch}
        helperText={mismatch ? "The two passwords don't match" : " "}
        required
        fullWidth
      />
    </>
  );
}

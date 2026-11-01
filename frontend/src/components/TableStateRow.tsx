import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

// The one row a table shows instead of data: loading, a failed load (with
// Retry), or empty (say what will appear here and how it gets there).
// Renders nothing once there are rows to show.
export function TableStateRow({
  colSpan,
  loading = false,
  error = null,
  onRetry,
  empty,
  count,
}: {
  colSpan: number;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty: string;
  count: number;
}) {
  if (count > 0 && !error) return null;
  return (
    <TableRow>
      <TableCell colSpan={colSpan} sx={{ py: 2 }}>
        {loading && count === 0 ? (
          <LinearProgress aria-label="Loading" sx={{ maxWidth: 240, mx: "auto" }} />
        ) : error ? (
          <Alert
            severity="error"
            action={
              onRetry && (
                <Button color="inherit" size="small" onClick={onRetry}>
                  Retry
                </Button>
              )
            }
          >
            {error}
          </Alert>
        ) : (
          <Typography variant="body2" sx={{ textAlign: "center", color: "text.disabled", fontStyle: "italic" }}>
            {empty}
          </Typography>
        )}
      </TableCell>
    </TableRow>
  );
}

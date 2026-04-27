import {
  type ExecutionStatus,
  STATUS_LABELS,
  STATUS_STYLES,
} from "@/lib/format";

export function ExecutionStatusBadge({
  status,
}: {
  status: ExecutionStatus;
}) {
  const cls = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-700 border-gray-200";
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span
      className={
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border " +
        cls
      }
    >
      {label}
    </span>
  );
}

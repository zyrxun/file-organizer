def apply_date_filter(
    files: list[dict],
    date_type: str,
    from_ts: float | None,
    to_ts: float | None,
) -> list[dict]:
    key = "mtime" if date_type == "modified" else "ctime"
    return [
        f for f in files
        if (from_ts is None or f[key] >= from_ts)
        and (to_ts is None or f[key] <= to_ts)
    ]

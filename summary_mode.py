# formatting.py
def fmt_price(x):
    if x is None:
        return "—"
    try:
        # не используем научную нотацию
        s = f"{float(x):.8f}".rstrip("0").rstrip(".")
        return s
    except Exception:
        return str(x)

def h(title: str) -> str:
    return f"\n<b>{title}</b>\n"

def bullet(line: str) -> str:
    return f"• {line}\n"

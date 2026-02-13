# funding_flow.py

def funding_flow_ok(symbol: str) -> bool:
    """
    Старый слой (если где-то ещё импортируется).
    Безопасная заглушка, чтобы бот не падал.
    """
    return False


def funding_crowd_ok(symbol: str) -> bool:
    """
    PRO слой: сигнал 'толпы'.
    Пока безопасная заглушка — позже подключим реальные funding/OI.
    """
    return False

def format_money(x: float) -> str:
    whole, frac = f"{x:.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return "$" + ",".join(groups) + "." + frac

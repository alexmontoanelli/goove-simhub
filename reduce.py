"""Redução de um array de LEDs RGB para uma única cor."""

from collections import Counter


def average(leds):
    if not leds:
        return (0, 0, 0)
    n = len(leds)
    r = sum(c[0] for c in leds)
    g = sum(c[1] for c in leds)
    b = sum(c[2] for c in leds)
    return (round(r / n), round(g / n), round(b / n))


def dominant(leds):
    if not leds:
        return (0, 0, 0)

    # quantiza em passos de 16 para agrupar tons próximos
    def q(c):
        return (c[0] // 16, c[1] // 16, c[2] // 16)

    counts = Counter(q(c) for c in leds)
    qbest, _ = counts.most_common(1)[0]
    # média dos LEDs que caem no bucket vencedor (cor mais fiel)
    members = [c for c in leds if q(c) == qbest]
    return average(members)


def luminance(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b

"""Build a connected 47-cell terrain atlas from a single repeating texture."""

from math import hypot

from PIL import Image


# Cardinal N/E/S/W = 1/2/4/8. Diagonal NE/SE/SW/NW = 16/32/64/128.
CORNERS = ((1, 8, 128), (1, 2, 16), (4, 2, 32), (4, 8, 64))
MASKS = tuple(mask for mask in range(256) if all(
    not mask & diagonal or mask & (vertical | horizontal) == vertical | horizontal
    for vertical, horizontal, diagonal in CORNERS))
GRID = (8, 6)


def build(texture):
    """Round convex corners and shade exposed edges and concave corners.

    Distances on a joined edge depend only on occupancy around its two
    vertices. Both tiles therefore produce the same boundary pixels.
    """
    width, height = texture.size
    radius = max(3, min(width, height) // 6)
    atlas = Image.new('RGBA', (width * GRID[0], height * GRID[1]))
    source = texture.load()
    for index, mask in enumerate(MASKS):
        tile = texture.copy()
        pixels = tile.load()
        for y in range(height):
            dy = min(y, height - 1 - y)
            for x in range(width):
                dx = min(x, width - 1 - x)
                top = y < height / 2
                left = x < width / 2
                vertical, horizontal, diagonal = CORNERS[(0 if left else 1) if top else (3 if left else 2)]
                v, h = bool(mask & vertical), bool(mask & horizontal)
                if not v and not h:
                    # Circular exterior with a tangent at each exposed edge.
                    distance = radius - hypot(max(0, radius - dx), max(0, radius - dy))
                    if distance < 0:
                        pixels[x, y] = (0, 0, 0, 0)
                        continue
                    distance = min(distance, dx, dy)
                elif not v:
                    distance = dy
                elif not h:
                    distance = dx
                elif not mask & diagonal:
                    distance = hypot(dx, dy)
                else:
                    continue
                if distance < radius:
                    red, green, blue, _ = source[x, y]
                    light = 1 + .30 * (1 - distance / radius) if distance < 2 else 1 - .22 * (1 - distance / radius)
                    pixels[x, y] = (*[min(255, round(channel * light)) for channel in (red, green, blue)], 255)
        atlas.paste(tile, (index % GRID[0] * width, index // GRID[0] * height))
    return atlas


def check_joins(cells):
    """Check every connected edge against others with the same vertex occupancy."""
    edges = {}
    for mask, cell in zip(MASKS, cells):
        w, h = cell.size
        for bit, diagonal_a, diagonal_b, axis, rect in (
            (1, 128, 16, 'vertical', (0, 0, w, 1)),
            (4, 64, 32, 'vertical', (0, h - 1, w, h)),
            (8, 128, 64, 'horizontal', (0, 0, 1, h)),
            (2, 16, 32, 'horizontal', (w - 1, 0, w, h)),
        ):
            if mask & bit:
                key = (axis, bool(mask & diagonal_a), bool(mask & diagonal_b))
                pixels = cell.crop(rect).tobytes()
                if edges.setdefault(key, pixels) != pixels:
                    raise ValueError(f'Terrain blob has a mismatched connected edge at mask {mask}')
    if cells[0].getpixel((0, 0))[3] != 0 or cells[-1].getchannel('A').getextrema() != (255, 255):
        raise ValueError('Terrain blob requires exposed corners and an opaque center tile')

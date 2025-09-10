from typing import TypeAlias

HexColor: TypeAlias = str  # A color represented as a hex string, e.g., "#RRGGBB"
RGBNormalized: TypeAlias = tuple[float, float, float]  # A color represented as normalized RGB values (0-1)
RGB: TypeAlias = tuple[int, int, int]  # A color represented as RGB values (0-255)
HSVNormalized: TypeAlias = tuple[float, float, float]  # A color represented in HSV color space
ColorByte: TypeAlias = int  # A single byte value for a color channel (0-255)
ColorFloat: TypeAlias = float  # A single float value for a color channel (0.0-1.0)
RGBByte: TypeAlias = ColorByte
Hue: TypeAlias = ColorFloat  # Hue value (0.0-1.0)
Saturation: TypeAlias = ColorFloat  # Saturation value (0.0-1.0)
Value: TypeAlias = ColorFloat  # Value/Brightness (0.0-1.0)

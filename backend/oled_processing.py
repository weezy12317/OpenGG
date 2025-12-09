from PIL import Image

# --- HARDWARE CONSTANTS ---
# The Apex Pro OLED is a 128x40 pixel monochrome display.
# Data is packed as 1 bit per pixel.
# Total Bytes = (128 * 40) / 8 = 640 bytes.
OLED_WIDTH = 128
OLED_HEIGHT = 40
BUFFER_SIZE = 640

def process_image_for_oled(image_input):
    """
    Prepares an image file or object for display on the hardware.

    Pipeline:
    1. Load image.
    2. Handle alpha transparency (composite over black).
    3. Resize to 128x40 (stretching).
    4. Dither and convert to 1-bit monochrome.
    5. Pack into raw byte buffer.

    Args:
        image_input (str | PIL.Image): File path or PIL Image object.

    Returns:
        list[int]: A list of 640 integers representing the raw bitmap data.
    """
    # 1. Load Image
    if isinstance(image_input, str):
        try:
            img = Image.open(image_input)
        except OSError:
            # Return blank buffer if file not found/invalid
            return create_blank_image()
    else:
        img = image_input

    # 2. Handle Transparency (RGBA)
    # Converting transparent pixels directly to '1' (white) often results in visual noise.
    # We compost pixel alpha onto a black background first to preserve the intended look.
    if img.mode == 'RGBA':
        background = Image.new("RGB", img.size, (0, 0, 0))
        background.paste(img, mask=img.split()[3]) # Channel 3 is Alpha
        img = background

    # 3. Resize
    # Use LANCZOS filter for high-quality downscaling to preserve details.
    # Note: This forcibly stretches the aspect ratio to fit the 128x40 screen.
    img = img.resize((OLED_WIDTH, OLED_HEIGHT), Image.Resampling.LANCZOS)

    # 4. Convert to 1-Bit Monochrome
    # convert("1") applies Floyd-Steinberg dithering by default, which simulates greyscale
    # using dot patterns. This looks much better than simple thresholding for photos.
    img = img.convert("1")

    # 5. Export Raw Bytes
    # Get the raw 1-bit per pixel data.
    data = img.tobytes()

    # 6. Safety Padding / Truncating
    # The USB protocol requires exactly 640 bytes. Mismatched lengths can crash the controller.
    if len(data) != BUFFER_SIZE:
        if len(data) < BUFFER_SIZE:
            # Pad with zeroes (black) if too short
            data = data + b'\x00' * (BUFFER_SIZE - len(data))
        else:
            # Truncate if too long
            data = data[:BUFFER_SIZE]

    # Convert bytes to list of integers for the USB packet builder
    return list(data)

def create_blank_image():
    """Returns a completely black 640-byte buffer to clear the screen."""
    return [0] * BUFFER_SIZE

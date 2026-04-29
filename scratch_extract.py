import re
import os
import base64

svg_path = r"c:\Users\Crist\OneDrive\Documentos\GitHub\pdf reader\instruçoes\modeloDePagina.svg"
out_dir = r"c:\Users\Crist\OneDrive\Documentos\GitHub\pdf reader\assets"

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

with open(svg_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all base64 images
pattern = r'data:image/png;base64,([A-Za-z0-9+/=]+)'
matches = re.findall(pattern, content)

for i, match in enumerate(matches):
    img_data = base64.b64decode(match)
    out_path = os.path.join(out_dir, f"extracted_{i}.png")
    with open(out_path, 'wb') as img_file:
        img_file.write(img_data)
    print(f"Saved {out_path}")

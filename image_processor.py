import io
import os
import requests
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client, Client
import uuid

load_dotenv('.env')

class ImageProcessor:
    def __init__(self):
        url = os.environ.get('SUPABASE_URL')
        # Supabase bucket logic removed: Images will be uploaded directly to eBay or WordPress

    def download_image_to_memory(self, url: str) -> io.BytesIO:
        """Downloads an image from a URL directly into RAM."""
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        return io.BytesIO(response.content)

    def process_and_compress_image(self, image_stream: io.BytesIO, apply_watermark: bool = True) -> io.BytesIO:
        """
        1. Strips all EXIF data by creating a new Image object.
        2. Applies a transparent watermark to the bottom right corner (if available).
        3. Compresses the image to WebP format to save space.
        Returns the optimized image as a BytesIO stream.
        """
        # Open the image using PIL
        original_img = Image.open(image_stream)
        
        # 1. Strip EXIF by copying data to a fresh Image object
        # Convert to RGBA first to handle transparency rules if any, then to RGB if needed
        if original_img.mode != 'RGBA':
            original_img = original_img.convert('RGBA')
            
        clean_img = Image.new(original_img.mode, original_img.size)
        clean_img.putdata(list(original_img.getdata()))
        
        # 2. Apply Watermark
        if apply_watermark and os.path.exists(self.watermark_path):
            try:
                watermark = Image.open(self.watermark_path).convert('RGBA')
                
                # Resize watermark to 20% of the image width
                wm_width = int(clean_img.width * 0.2)
                aspect_ratio = watermark.height / watermark.width
                wm_height = int(wm_width * aspect_ratio)
                watermark = watermark.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
                
                # Calculate position (Bottom Right corner with a small padding)
                padding = int(clean_img.width * 0.05)
                position = (clean_img.width - wm_width - padding, clean_img.height - wm_height - padding)
                
                # Create a transparent layer the size of the base image
                transparent_layer = Image.new('RGBA', clean_img.size, (0,0,0,0))
                transparent_layer.paste(watermark, position, watermark)
                
                # Composite the watermark layer over the base image
                clean_img = Image.alpha_composite(clean_img, transparent_layer)
            except Exception as e:
                print(f"Failed to apply watermark: {e}")
                
        # Prepare for saving (WebP supports RGBA, so we can keep it RGBA)
        output_stream = io.BytesIO()
        
        # 3. Compress to WebP
        # Quality 80 gives incredible reduction with virtually no visible loss
        clean_img.save(output_stream, format="WEBP", quality=80, method=6)
        output_stream.seek(0)
        
        return output_stream

    def get_base64_image(self, image_stream: io.BytesIO) -> str:
        """
        Converts a BytesIO stream to a base64 encoded string.
        """
        import base64
        return base64.b64encode(image_stream.read()).decode('utf-8')

    def process_url_to_base64(self, url: str) -> str:
        """Master function: Downloads, processes, and returns the image as a Base64 string for direct upload to eBay."""
        try:
            raw_stream = self.download_image_to_memory(url)
            # eBay EPS prefers JPG or PNG. WebP sometimes fails in UploadSiteHostedPictures. 
            # So we will output as JPEG from the processor.
            
            # Re-implementing the process logic inline to change output to JPEG
            original_img = Image.open(raw_stream)
            if original_img.mode != 'RGB':
                original_img = original_img.convert('RGB')
                
            clean_img = Image.new(original_img.mode, original_img.size)
            clean_img.putdata(list(original_img.getdata()))
            
            if apply_watermark := True and os.path.exists(self.watermark_path):
                try:
                    watermark = Image.open(self.watermark_path).convert('RGBA')
                    wm_width = int(clean_img.width * 0.2)
                    aspect_ratio = watermark.height / watermark.width
                    wm_height = int(wm_width * aspect_ratio)
                    watermark = watermark.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
                    
                    padding = int(clean_img.width * 0.05)
                    position = (clean_img.width - wm_width - padding, clean_img.height - wm_height - padding)
                    
                    # Create RGBA version of clean image to apply alpha composite
                    clean_rgba = clean_img.convert('RGBA')
                    
                    transparent_layer = Image.new('RGBA', clean_rgba.size, (0,0,0,0))
                    transparent_layer.paste(watermark, position, watermark)
                    
                    clean_rgba = Image.alpha_composite(clean_rgba, transparent_layer)
                    # Convert back to RGB for JPEG save
                    clean_img = clean_rgba.convert('RGB')
                except Exception as e:
                    print(f"Failed to apply watermark: {e}")
            
            output_stream = io.BytesIO()
            clean_img.save(output_stream, format="JPEG", quality=85)
            output_stream.seek(0)
            
            return self.get_base64_image(output_stream)
            
        except Exception as e:
            print(f"Full pipeline error: {e}")
            return ""

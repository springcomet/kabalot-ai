# %pip install openai
# %pip install pymupdf
# %pip install Pillow
# %pip install dropbox

from openai import OpenAI
import fitz  # PyMuPDF
import io
import os
from PIL import Image
import mimetypes
import base64
from io import BytesIO
import json
import dropbox
import re
from pathlib import Path
from datetime import datetime



@staticmethod
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def pdf_to_base64_images(pdf_path):
    #Handles PDFs with multiple pages
    pdf_document = fitz.open(pdf_path)
    base64_images = []
    temp_image_paths = []

    total_pages = len(pdf_document)

    for page_num in range(total_pages):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        temp_image_path = f"temp_page_{page_num}.png"
        img.save(temp_image_path, format="PNG")
        temp_image_paths.append(temp_image_path)
        base64_image = encode_image(temp_image_path)
        base64_images.append(base64_image)

    for temp_image_path in temp_image_paths:
        os.remove(temp_image_path)

    return base64_images

def jpg_to_base64_images(jpg_file_path):
    base64_images = []
    
    # Open the JPG file
    with Image.open(jpg_file_path) as img:
        # Convert the image to a BytesIO object
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        
        # Encode the BytesIO object to base64
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Append the base64 string to the list
        base64_images.append(img_base64)
    
    return base64_images

def extract_invoice_data(base64_image):
    system_prompt = f"""
    You are an OCR-like data extraction tool that extracts hotel invoice data from PDFs.
   
    1. Please extract the data in this invoice, grouping data according to theme/sub groups, and then output into JSON.

    2. Please keep the keys and values of the JSON in the original language. use native characters for the keys and values,
    dont encode them to characters like "utf-8" or "ascii".

    3. The type of data you might encounter in the invoice includes but is not limited to: supplier information such as name and identity number, itemized charges, invoice information,
   such as invoice number, taxes such as vat amount or price before vat, and total charges etc. 

    4. If the page contains no charge data, please output an empty JSON object and don't make up any data.

    5. If there are blank data fields in the invoice, please include them as "null" values in the JSON object.
    
    6. If there are tables in the invoice, capture all of the rows and columns in the JSON object. 
    Even if a column is blank, include it as a key in the JSON object with a null value.
    
    7. If a row is blank denote missing fields with "null" values. 
    
    8. Don't interpolate or make up data.

    9. Please maintain the table structure of the charges, i.e. capture all of the rows and columns in the JSON object.

    10. if the invoice is a vihicle related purchase the expcted vihicle number is 9160011

    11. add a last group named invoice_summary which repeates the values of the total charge, date of invoice, and invoice number. 
    these values should also be included in the relevant group and repeated in this group. 
    unlike other groups, in this group the key names should be in english as specified here.

    12. try to deduce if the invoice is for vehicle expences, office expences, clothing expences, 
    or food expences and include this in the JSON object in the invoice_summary group.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "extract the data in this invoice and output into JSON "},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "high"}}
                ]
            }
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content

def extract_from_multiple_pages(file_path):
    return [{'Details of Services Charged': [{'City': 'הרצליה', 'Zone': 'אזור התעשיה', 'License Plate': '62-728-55', 'Start Time': '15/01/2024 08:50', 'To Time': '15/01/2024 10:14', 'Minutes': '83:19', 'Charge': '8.61'}, {'City': 'רמת גן', 'Zone': 'הבימה ת"א חניון הבימה והיכל התרבות', 'License Plate': '91-600-11', 'Start Time': '26/12/2023 14:41', 'To Time': '26/12/2023 16:06', 'Minutes': '84:46', 'Charge': '8.90'}, {'City': 'תל-אביב', 'Zone': 'מרכז העיר 17:00-חניה חופשית או חניה בתשלום באזור', 'License Plate': '91-600-11', 'Start Time': '24/01/2024 07:57', 'To Time': '24/01/2024 09:38', 'Minutes': '38:04', 'Charge': '7.87'}], 'invoice_summary': {'total_charge': '25.38', 'date_of_invoice': '3/9/24', 'invoice_number': None, 'expense_type': 'vehicle'}}]
    mime_type, _ = mimetypes.guess_type(file_path)
    print(f"File type: {mime_type}")
    if mime_type == 'application/pdf':
        base64_images = pdf_to_base64_images(file_path)
    elif mime_type == 'image/jpeg':
        base64_images = jpg_to_base64_images(file_path)
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")

    entire_invoice = []
    for base64_image in base64_images:
        invoice_json = extract_invoice_data(base64_image)
        invoice_data = json.loads(invoice_json)
        entire_invoice.append(invoice_data)
    return entire_invoice


def main_extract(config):
    for input_dir in config["input_dirs"]:
        print(f"Extracting data from files in {input_dir}")
        for filename in os.listdir(input_dir):
            print(f"Extracting data from {filename}")
            file_path = os.path.join(input_dir, filename)
            if os.path.isfile(file_path):
                invoice = extract_from_multiple_pages(file_path)
                print(invoice)
                write_invoice(config, invoice)
                #upload_file_to_dropbox(config, file_path)

def get_safe_filename(invoice_data):
    # Handle both single invoice and list of invoices
    invoice_dict = invoice_data[0] if isinstance(invoice_data, list) else invoice_data
    
    # Safely navigate nested structure
    invoice_summary = invoice_dict.get('invoice_summary', {})
    invoice_number = invoice_summary.get('invoice_number')
    
    if not invoice_number:
        # Fallback to timestamp if no invoice number
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        invoice_number = f"invoice_{timestamp}"
    
    # Sanitize filename
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', str(invoice_number))
    return f"{safe_name}.json"

def write_invoice(config, invoice):
    output_dir = config["output_dir"]
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    invoice_number = get_safe_filename(invoice)
    filename  = invoice_number    
    output_file = os.path.join(output_dir, filename)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(invoice, f, ensure_ascii=False, indent=4)
    print(f"Data written to {output_file}")

def upload_file_to_dropbox(config, file):
    # Read credentials from creds file
   
    # Initialize Dropbox client
    dbx = dropbox.Dropbox(config["dropbox_access_token"])
    print("Initialized Dropbox client.")
    
    
    # Ensure the Dropbox path exists
    # try:
    #     dbx.files_create_folder_v2(dropbox_path)
    #     print(f"Created folder {dropbox_path} in Dropbox.")
    # except dropbox.exceptions.ApiError as e:
    #     if e.error.is_path() and e.error.get_path().is_conflict():
    #         print(f"Folder {dropbox_path} already exists.")
    #     else:
    #         raise e
    # Upload files from the local directory to the Dropbox path
    if os.path.isfile(filename):
        dropbox_file_path = os.path.join(config["dropbox_path"], filename)
        print(f'Attempting to upload {filename} to Dropbox:{dropbox_file_path}...')
        with open(filename, 'rb') as f:
            dbx.files_upload(f.read(), dropbox_file_path, mode=dropbox.files.WriteMode.overwrite)
        print(f"Uploaded {filename} to {dropbox_file_path}")
        # Create a shared link for the uploaded file
        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_file_path)
        file_link = shared_link_metadata.url
        print(f"Shared link for {filename}: {file_link}")
    else:
        print(f"Skipping {filename}, not a file.")
    return file_link

def load_config(config_file):
    required_fields = {
        "output_dir": "Output directory",
        "input_dirs": "Input directories",
        "upload_path": "Upload path",
        "dropbox_path": "Dropbox path"
    }
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Validate all required fields exist
    missing = [field for field, name in required_fields.items() 
              if not config.get(field)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
        
    return config

def get_dropbox_token(creds_file):
    """Read Dropbox access token from credentials file."""
    try:
        with open(creds_file, 'r', encoding='utf-8') as cred_file:
            creds = json.load(cred_file)
            dropbox_access_token = creds.get("dropbox")
            if not dropbox_access_token:
                raise ValueError("Dropbox access token not found in credentials file.")
            print("dropbox token: ", dropbox_access_token[-4:])
            return dropbox_access_token
    except FileNotFoundError:
        raise FileNotFoundError(f"Credentials file not found: {creds_file}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in credentials file: {creds_file}")

# Example usage
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)
config_file = './config/kabalot.json'
creds_file='./secrets/secrets.json'

# Read JSON file to get the Dropbox path
config = load_config(config_file)
dropbox_access_token = get_dropbox_token(creds_file)
print("config: ", config)
config["dropbox_access_token"] = dropbox_access_token
main_extract(config)

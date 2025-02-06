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

    2. Please keep the keys and values of the JSON in the original language. 

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

def extract_from_multiple_pages(base64_images, original_filename, output_directory):
    entire_invoice = []

    for base64_image in base64_images:
        invoice_json = extract_invoice_data(base64_image)
        invoice_data = json.loads(invoice_json)
        entire_invoice.append(invoice_data)

    # Ensure the output directory exists
    os.makedirs(output_directory, exist_ok=True)

    # Get the file name without extension and the extension separately
    file_name, file_extension = os.path.splitext(original_filename)

    # Replace the extension with '_extracted.json'
    output_filename = os.path.join(output_directory, f"{file_name}_extracted.json")
    
    # Save the entire_invoice list as a JSON file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entire_invoice, f, ensure_ascii=False, indent=4)
    return output_filename


def main_extract(read_path, write_path):
    for filename in os.listdir(read_path):
        print(f"Extracting data from {filename}")
        file_path = os.path.join(read_path, filename)
        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            print(f"File type: {mime_type}")
            if mime_type == 'application/pdf':
                base64_images = pdf_to_base64_images(file_path)
            elif mime_type == 'image/jpeg':
                base64_images = jpg_to_base64_images(file_path)
            else:
                raise ValueError(f"Unsupported file type: {mime_type}")
        extract_from_multiple_pages(base64_images, filename, write_path)



def upload_files_to_dropbox(token, json_file_path, local_directory):
    # Read credentials from creds file
   
    # Initialize Dropbox client
    dbx = dropbox.Dropbox(token)
    print("Initialized Dropbox client.")
    
    # Read JSON file to get the Dropbox path
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        dropbox_path = data.get("dropbox_path")
    
    if not dropbox_path:
        raise ValueError("Dropbox path not found in JSON file.")
    
    # Ensure the Dropbox path exists
    # try:
    #     dbx.files_create_folder_v2(dropbox_path)
    #     print(f"Created folder {dropbox_path} in Dropbox.")
    # except dropbox.exceptions.ApiError as e:
    #     if e.error.is_path() and e.error.get_path().is_conflict():
    #         print(f"Folder {dropbox_path} already exists.")
    #     else:
    #         raise e
    file_links = {}
    # Upload files from the local directory to the Dropbox path
    for filename in os.listdir(local_directory):
        local_file_path = os.path.join(local_directory, filename)
        if os.path.isfile(local_file_path):
            dropbox_file_path = os.path.join(dropbox_path, filename)
            print(f'Attempting to upload {filename} to Dropbox:{dropbox_file_path}...')
            with open(local_file_path, 'rb') as f:
                dbx.files_upload(f.read(), dropbox_file_path, mode=dropbox.files.WriteMode.overwrite)
            print(f"Uploaded {filename} to {dropbox_file_path}")
            # Create a shared link for the uploaded file
            shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_file_path)
            file_links[filename] = shared_link_metadata.url
        else:
            print(f"Skipping {filename}, not a file.")
    print("All files uploaded successfully.")
    print(file_links)

# Example usage
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)
read_path= "./in/"
write_path= "./out/data.json"
json_file_path = './config/dropbox.json'
local_directory = './in'
creds_file='./secrets/secrets.json'

with open(creds_file, 'r', encoding='utf-8') as cred_file:
    creds = json.load(cred_file)
    dropbox_access_token = creds.get("dropbox")
    if not dropbox_access_token:
        raise ValueError("Dropbox access token not found in environment variables.")
    print("dropbox token: ", dropbox_access_token[-4:])


main_extract(local_directory, write_path)

#upload_files_to_dropbox(dropbox_access_token, json_file_path, local_directory)

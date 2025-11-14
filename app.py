import os
import logging
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# --- Configuration ---
# It is highly recommended to set these as environment variables for security.
LEMLIST_API_KEY = os.getenv('LEMLIST_API_KEY')
CAMPAIGN_NAME = "website_leads"  # Fixed campaign name for RB2B leads

# --- Logging Setup ---
# This fulfills the logging requirement from the BRD.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("webhook_handler.log"), # Log to a file
        logging.StreamHandler() # Log to console
    ]
)

# --- Flask App Initialization ---
app = Flask(__name__)

# Global variable to store the campaign ID once found/created
CAMPAIGN_ID = None


def get_or_create_campaign():
    """
    Checks if the 'website_leads' campaign exists in lemlist.
    If it exists, returns its ID. If not, creates it and returns the new ID.
    """
    global CAMPAIGN_ID
    
    if CAMPAIGN_ID:
        return CAMPAIGN_ID
    
    # Check if API key is loaded
    if not LEMLIST_API_KEY:
        logging.error("LEMLIST_API_KEY is not set. Please check your .env file.")
        raise ValueError("Missing LEMLIST_API_KEY")
    
    logging.info(f"Using API key: {LEMLIST_API_KEY[:8]}..." if len(LEMLIST_API_KEY) > 8 else "API key too short")
    # IMPORTANT: lemlist uses Basic Auth with EMPTY username and API key as password
    # This creates the format ":APIKEY" as required by lemlist docs
    auth = ('', LEMLIST_API_KEY)
    
    # 1. Try to get all campaigns and find 'website_leads'
    try:
        logging.info(f"Checking if campaign '{CAMPAIGN_NAME}' exists in lemlist...")
        response = requests.get('https://api.lemlist.com/api/campaigns', auth=auth)
        
        # Log the response details before raising error
        logging.info(f"GET campaigns response status: {response.status_code}")
        if response.status_code != 200:
            logging.error(f"Error response body: {response.text}")
        
        response.raise_for_status()
        
        campaigns = response.json()
        logging.info(f"Found {len(campaigns)} campaigns in lemlist")
        
        for campaign in campaigns:
            if campaign.get('name') == CAMPAIGN_NAME:
                CAMPAIGN_ID = campaign.get('_id')
                logging.info(f"Found existing campaign '{CAMPAIGN_NAME}' with ID: {CAMPAIGN_ID}")
                return CAMPAIGN_ID
        
        # 2. Campaign doesn't exist, create it
        logging.info(f"Campaign '{CAMPAIGN_NAME}' not found. Creating new campaign...")
        create_payload = {"name": CAMPAIGN_NAME}
        logging.info(f"Create campaign payload: {create_payload}")
        
        create_response = requests.post(
            'https://api.lemlist.com/api/campaigns',
            json=create_payload,
            auth=auth
        )
        
        logging.info(f"POST campaign response status: {create_response.status_code}")
        if create_response.status_code != 200 and create_response.status_code != 201:
            logging.error(f"Error response body: {create_response.text}")
        
        create_response.raise_for_status()
        
        new_campaign = create_response.json()
        CAMPAIGN_ID = new_campaign.get('_id')
        logging.info(f"Successfully created campaign '{CAMPAIGN_NAME}' with ID: {CAMPAIGN_ID}")
        return CAMPAIGN_ID
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error while checking/creating campaign: {e}")
        raise

# --- Main Webhook Endpoint ---
@app.route('/rb2b-webhook', methods=['POST'])
def rb2b_webhook_receiver():
    """
    Receives visitor data from RB2B webhook, processes it,
    and creates a new contact in a specific lemlist campaign.
    """
    logging.info("=" * 80)
    logging.info("🎯 WEBHOOK REQUEST RECEIVED")
    logging.info("=" * 80)
    
    # Log request metadata
    logging.info(f"📍 Request Method: {request.method}")
    logging.info(f"📍 Request URL: {request.url}")
    logging.info(f"📍 Request Path: {request.path}")
    logging.info(f"📍 Remote Address: {request.remote_addr}")
    logging.info(f"📍 User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    logging.info(f"📍 Content Type: {request.headers.get('Content-Type', 'Unknown')}")
    
    # Log all headers (for debugging)
    logging.info("📋 Request Headers:")
    for header, value in request.headers.items():
        logging.info(f"   {header}: {value}")

    # 1. Receive and Parse Data from RB2B
    try:
        logging.info("🔄 Step 1: Parsing request body...")
        rb2b_data = request.get_json()
        
        if not rb2b_data:
            logging.error("❌ Request body is empty or not JSON.")
            return jsonify({"status": "error", "message": "Invalid request data"}), 400
        
        logging.info("✅ Successfully parsed JSON data")
        logging.info(f"📦 Raw RB2B Data ({len(rb2b_data)} fields):")
        for key, value in rb2b_data.items():
            logging.info(f"   {key}: {value}")
            
    except Exception as e:
        logging.error(f"❌ Could not parse JSON data from request: {e}")
        logging.error(f"   Raw request data: {request.data}")
        return jsonify({"status": "error", "message": "Failed to parse JSON"}), 400

    # 2. Extract and Validate Essential Data
    logging.info("🔄 Step 2: Extracting and validating email...")
    
    # Try multiple field name variations that RB2B might send
    work_email = rb2b_data.get("WorkEmail")
    business_email_field = rb2b_data.get("Business Email")
    email_field = rb2b_data.get("email")
    
    logging.info(f"   WorkEmail field: {work_email}")
    logging.info(f"   Business Email field: {business_email_field}")
    logging.info(f"   email field: {email_field}")
    
    business_email = work_email or business_email_field or email_field
    
    if not business_email:
        logging.warning("❌ No email found in any field - skipping lead")
        logging.warning("   Checked fields: WorkEmail, Business Email, email")
        return jsonify({"status": "skipped", "message": "Missing required field: email"}), 200
    
    logging.info(f"✅ Email found: {business_email}")

    # 3. Data Mapping: Map RB2B fields to lemlist fields
    logging.info("🔄 Step 3: Mapping RB2B fields to lemlist format...")
    
    # Standard lemlist fields + custom fields for additional RB2B data
    lemlist_payload = {
        "firstName": rb2b_data.get("FirstName") or rb2b_data.get("First Name"),
        "lastName": rb2b_data.get("LastName") or rb2b_data.get("Last Name"),
        "linkedinUrl": rb2b_data.get("LinkedIn URL") or rb2b_data.get("LinkedInUrl"),
        "jobTitle": rb2b_data.get("Title") or rb2b_data.get("jobTitle"),
        "companyName": rb2b_data.get("CompanyName") or rb2b_data.get("Company Name"),
        "companyWebsite": rb2b_data.get("Website") or rb2b_data.get("companyWebsite"),
        "companyIndustry": rb2b_data.get("Industry") or rb2b_data.get("companyIndustry"),
        "companySize": rb2b_data.get("EstimatedEmployeeCount") or rb2b_data.get("Employee Count"),
        "city": rb2b_data.get("City"),
        "state": rb2b_data.get("State"),
        # Custom fields for additional RB2B data
        "zipcode": rb2b_data.get("Zipcode") or rb2b_data.get("zipcode"),
        "estimatedRevenue": rb2b_data.get("EstimateRevenue") or rb2b_data.get("Estimate Revenue")
    }
    
    logging.info(f"📋 Field mapping (before cleanup):")
    for key, value in lemlist_payload.items():
        status = "✅" if value else "⚠️ (empty)"
        logging.info(f"   {key}: {value} {status}")
    
    # Remove None values to keep payload clean
    lemlist_payload = {k: v for k, v in lemlist_payload.items() if v is not None}
    
    logging.info(f"✅ Final payload has {len(lemlist_payload)} fields: {list(lemlist_payload.keys())}")
    
    # 4. Create Contact in lemlist
    try:
        logging.info("🔄 Step 4: Getting campaign ID...")
        # Ensure campaign exists and get its ID
        campaign_id = get_or_create_campaign()
        logging.info(f"✅ Campaign ID obtained: {campaign_id}")
        
        # Construct the specific API endpoint URL required by lemlist
        lemlist_api_url = f"https://api.lemlist.com/api/campaigns/{campaign_id}/leads/{business_email}"
        
        logging.info("🔄 Step 5: Preparing lemlist API request...")
        logging.info(f"📍 API URL: {lemlist_api_url}")
        logging.info(f"📦 Payload being sent to lemlist:")
        for key, value in lemlist_payload.items():
            logging.info(f"   {key}: {value}")

        # lemlist uses Basic Authentication with EMPTY username and API key as password
        # This creates the format ":APIKEY" as required by lemlist docs
        auth = ('', LEMLIST_API_KEY)

        headers = {
            "Content-Type": "application/json"
        }

        logging.info(f"🚀 Sending POST request to lemlist for: {business_email}")
        response = requests.post(lemlist_api_url, json=lemlist_payload, auth=auth, headers=headers)

        logging.info(f"📥 Response received from lemlist")
        logging.info(f"   Status Code: {response.status_code}")
        logging.info(f"   Response Headers: {dict(response.headers)}")
        logging.info(f"   Response Body: {response.text}")

        # 5. Handle lemlist API Response
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status() 

        logging.info("=" * 80)
        logging.info(f"✅ SUCCESS! Contact created in lemlist")
        logging.info(f"   Email: {business_email}")
        logging.info(f"   Campaign: {CAMPAIGN_NAME}")
        logging.info(f"   Response: {response.json()}")
        logging.info("=" * 80)
        return jsonify({"status": "success", "message": "Contact created in lemlist"}), 201

    except requests.exceptions.HTTPError as http_err:
        logging.error("=" * 80)
        logging.error(f"❌ HTTP ERROR from lemlist API")
        logging.error(f"   Error: {http_err}")
        logging.error(f"   Status Code: {response.status_code}")
        logging.error(f"   Response Body: {response.text}")
        logging.error(f"   Email attempted: {business_email}")
        logging.error(f"   Campaign ID: {campaign_id}")
        logging.error("=" * 80)
        return jsonify({"status": "error", "message": "Failed to create contact in lemlist", "details": response.text}), 502
    except requests.exceptions.RequestException as req_err:
        logging.error("=" * 80)
        logging.error(f"❌ NETWORK ERROR connecting to lemlist")
        logging.error(f"   Error: {req_err}")
        logging.error("=" * 80)
        return jsonify({"status": "error", "message": "Network error connecting to lemlist"}), 503
    except Exception as e:
        logging.error("=" * 80)
        logging.error(f"❌ UNEXPECTED ERROR occurred")
        logging.error(f"   Error: {e}")
        logging.error(f"   Error Type: {type(e).__name__}")
        logging.error("=" * 80)
        return jsonify({"status": "error", "message": "An internal server error occurred"}), 500


# --- Main Execution Block ---
if __name__ == '__main__':
    # Ensure campaign exists before starting the server
    try:
        logging.info("=" * 60)
        logging.info("Starting RB2B to lemlist Webhook Server")
        logging.info("=" * 60)
        get_or_create_campaign()
        logging.info(f"Campaign '{CAMPAIGN_NAME}' is ready to receive leads")
        logging.info("=" * 60)
    except Exception as e:
        logging.error(f"Failed to initialize campaign: {e}")
        logging.error("Server will not start. Please check your lemlist API key.")
        exit(1)
    
    # The host '0.0.0.0' makes the server accessible from any IP address,
    # which is necessary for deployment.
    # The default port is 5000.
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))


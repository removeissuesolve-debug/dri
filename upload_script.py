import os
import re
import requests
import random
import string
import time
import gdown
from pathlib import Path
from datetime import datetime

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_NAME = os.environ.get('REPO_NAME')
DRIVE_FILE = 'drive.txt'
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def generate_random_suffix(length=6):
    """Generate random suffix for uniqueness"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def extract_drive_file_id(url):
    """Extract file ID from Google Drive URL"""
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
        r'download\?id=([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_drive_file_info(file_id):
    """Get file information from Google Drive"""
    try:
        api_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=name,size"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('name', f'video_{file_id[:8]}.mp4')
        else:
            return f'video_{file_id[:8]}.mp4'
    except:
        return f'video_{file_id[:8]}.mp4'

def download_from_drive_gdown(file_id, output_path, retry_count=0):
    """
    Download files from Google Drive using gdown library
    This handles virus scan warning automatically for large files
    """
    if retry_count >= MAX_RETRIES:
        print(f"✗ Max retries ({MAX_RETRIES}) reached for download")
        return False
    
    if retry_count > 0:
        print(f"🔄 Retry attempt {retry_count}/{MAX_RETRIES}")
        time.sleep(RETRY_DELAY)
    
    print(f"📥 Downloading file ID: {file_id}")
    
    try:
        # gdown automatically handles virus scan warning
        url = f"https://drive.google.com/uc?id={file_id}"
        
        # Download with progress bar (removed fuzzy parameter for compatibility)
        gdown.download(url, output_path, quiet=False)
        
        # Verify file exists and has content
        if not os.path.exists(output_path):
            print("✗ File was not downloaded")
            return download_from_drive_gdown(file_id, output_path, retry_count + 1)
        
        file_size = os.path.getsize(output_path)
        
        if file_size == 0:
            print("✗ Downloaded file is empty")
            os.remove(output_path)
            return download_from_drive_gdown(file_id, output_path, retry_count + 1)
        
        print(f"✓ Download completed: {file_size / (1024*1024):.2f} MB")
        return True
        
    except Exception as e:
        print(f"✗ Error downloading: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        
        # Check if it's a permission/access error
        if "access denied" in str(e).lower() or "permission" in str(e).lower():
            print("⚠ File may not be publicly accessible")
            return False
        
        # Retry on other errors
        return download_from_drive_gdown(file_id, output_path, retry_count + 1)

def download_large_file_fallback(file_id, output_path):
    """
    Fallback method using requests with manual virus scan handling
    Used if gdown fails
    """
    print("🔄 Trying fallback download method...")
    
    url = "https://drive.google.com/uc?export=download"
    session = requests.Session()
    
    try:
        # First request
        response = session.get(url, params={'id': file_id}, stream=True, timeout=120)
        
        # Look for confirmation token in cookies
        token = None
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                token = value
                break
        
        # If token found, make confirmed request
        if token:
            params = {'id': file_id, 'confirm': token}
            response = session.get(url, params=params, stream=True, timeout=120)
        
        # Check for HTML response (confirmation page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            # Try to extract confirmation token from HTML
            html_content = b''
            for chunk in response.iter_content(chunk_size=8192):
                html_content += chunk
                if len(html_content) > 100000:  # Don't read too much
                    break
            
            # Look for confirm parameter in HTML
            match = re.search(rb'confirm=([^&"\']+)', html_content)
            if match:
                confirm_token = match.group(1).decode('utf-8', errors='ignore')
                params = {'id': file_id, 'confirm': confirm_token}
                response = session.get(url, params=params, stream=True, timeout=120)
        
        # Download the file
        total_size = int(response.headers.get('content-length', 0))
        
        if total_size > 0:
            print(f"File size: {total_size / (1024*1024):.2f} MB")
        
        with open(output_path, 'wb') as f:
            downloaded = 0
            chunk_size = 32768
            last_update = time.time()
            
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if time.time() - last_update > 2:
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\rProgress: {progress:.1f}% ({downloaded/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB)", end='')
                        else:
                            print(f"\rDownloaded: {downloaded/(1024*1024):.1f} MB", end='')
                        last_update = time.time()
        
        print()
        
        if os.path.getsize(output_path) == 0:
            print("✗ Downloaded file is empty")
            os.remove(output_path)
            return False
        
        print(f"✓ Download completed")
        return True
        
    except Exception as e:
        print(f"✗ Fallback download failed: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return False

def download_from_drive(file_id, output_path, retry_count=0):
    """
    Main download function - tries gdown first, then fallback
    """
    # Try gdown first (best for large files)
    success = download_from_drive_gdown(file_id, output_path, retry_count)
    
    # If gdown fails and we haven't exceeded retries, try fallback
    if not success and retry_count < MAX_RETRIES:
        print("⚠ gdown failed, trying alternative method...")
        time.sleep(RETRY_DELAY)
        success = download_large_file_fallback(file_id, output_path)
    
    return success

def get_all_releases(repo_name, token):
    """Get all existing releases"""
    url = f"https://api.github.com/repos/{repo_name}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def create_unique_release(repo_name, base_name, token, retry_count=0):
    """Create release with unique name and retry logic"""
    if retry_count >= MAX_RETRIES:
        print(f"✗ Max retries ({MAX_RETRIES}) reached for release creation")
        return None
    
    if retry_count > 0:
        print(f"🔄 Retry attempt {retry_count}/{MAX_RETRIES} for release creation")
        time.sleep(RETRY_DELAY)
    
    existing_releases = get_all_releases(repo_name, token)
    existing_tags = [r['tag_name'] for r in existing_releases]
    
    # Generate unique tag
    tag_name = base_name
    counter = 1
    
    while tag_name in existing_tags:
        suffix = generate_random_suffix()
        tag_name = f"{base_name}-{suffix}"
        counter += 1
        
        if counter > 10:
            tag_name = f"{base_name}-{int(time.time())}"
            break
    
    url = f"https://api.github.com/repos/{repo_name}/releases"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "tag_name": tag_name,
        "name": tag_name,
        "body": f"Auto-uploaded video - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "draft": False,
        "prerelease": False
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 201:
            print(f"✓ Created release: {tag_name}")
            return response.json()
        else:
            print(f"✗ Error creating release: {response.status_code}")
            print(response.text)
            
            if response.status_code >= 500 or response.status_code == 429:
                return create_unique_release(repo_name, base_name, token, retry_count + 1)
            return None
            
    except Exception as e:
        print(f"✗ Exception creating release: {e}")
        return create_unique_release(repo_name, base_name, token, retry_count + 1)

def upload_to_release(repo_name, release_id, file_path, token, retry_count=0):
    """Upload file to GitHub release with retry logic"""
    if retry_count >= MAX_RETRIES:
        print(f"✗ Max retries ({MAX_RETRIES}) reached for upload")
        return None
    
    if retry_count > 0:
        print(f"🔄 Retry attempt {retry_count}/{MAX_RETRIES} for upload")
        time.sleep(RETRY_DELAY)
    
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    print(f"📤 Uploading: {file_name} ({file_size / (1024*1024):.2f} MB)")
    
    url = f"https://uploads.github.com/repos/{repo_name}/releases/{release_id}/assets?name={file_name}"
    
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/octet-stream"
    }
    
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(url, data=f, headers=headers, timeout=900)
        
        if response.status_code == 201:
            asset_data = response.json()
            download_url = asset_data['browser_download_url']
            print(f"✓ Upload successful!")
            print(f"🔗 Download URL: {download_url}")
            return download_url
        else:
            print(f"✗ Upload failed: {response.status_code}")
            print(response.text)
            
            if response.status_code >= 500 or response.status_code == 408:
                return upload_to_release(repo_name, release_id, file_path, token, retry_count + 1)
            return None
            
    except requests.exceptions.Timeout:
        print(f"✗ Upload timeout")
        return upload_to_release(repo_name, release_id, file_path, token, retry_count + 1)
        
    except Exception as e:
        print(f"✗ Error uploading: {e}")
        return upload_to_release(repo_name, release_id, file_path, token, retry_count + 1)

def process_drive_file():
    """Main processing function"""
    print("=" * 80)
    print("🚀 GitHub Actions - Drive to Release Uploader")
    print("=" * 80)
    
    if not os.path.exists(DRIVE_FILE):
        print(f"✗ {DRIVE_FILE} not found!")
        return
    
    # Read drive.txt
    with open(DRIVE_FILE, 'r') as f:
        lines = f.readlines()
    
    github_links = []
    failed_links = []  # Store failed Drive links with reason
    temp_folder = "temp_videos"
    os.makedirs(temp_folder, exist_ok=True)
    
    total_drive_links = sum(1 for line in lines if 'drive.google.com' in line.strip())
    processed_count = 0
    
    print(f"\n📊 Found {total_drive_links} Drive links to process")
    print("-" * 80)
    
    for idx, line in enumerate(lines, 1):
        line = line.strip()
        
        if not line or line.startswith('#'):
            continue
        
        # If already a GitHub link, keep it
        if 'github.com' in line or 'githubusercontent.com' in line:
            print(f"\n[{idx}/{len(lines)}] ✓ Already GitHub link - keeping it")
            github_links.append(line)
            continue
        
        # Check if it's a Drive URL
        if 'drive.google.com' not in line:
            print(f"\n[{idx}/{len(lines)}] ⚠ Not a Drive URL - skipping")
            continue
        
        processed_count += 1
        print(f"\n{'='*80}")
        print(f"🎬 [{processed_count}/{total_drive_links}] Processing Drive URL")
        print(f"🔗 URL: {line[:70]}...")
        
        # Extract file ID
        file_id = extract_drive_file_id(line)
        if not file_id:
            print("✗ Could not extract file ID - skipping")
            failed_links.append({
                'url': line,
                'reason': 'Invalid Drive URL - Could not extract file ID',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue
        
        print(f"🆔 File ID: {file_id}")
        
        # Get original filename
        original_name = get_drive_file_info(file_id)
        base_name = Path(original_name).stem
        extension = Path(original_name).suffix or '.mp4'
        
        # Generate filename
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', base_name)[:50]
        filename = f"{safe_name}{extension}"
        temp_path = os.path.join(temp_folder, filename)
        
        print(f"📝 Filename: {filename}")
        
        # Download from Drive
        print(f"\n{'─'*80}")
        print("📥 STEP 1/3: Downloading from Google Drive")
        print(f"{'─'*80}")
        
        if not download_from_drive(file_id, temp_path):
            print("✗ Download failed after all attempts - skipping this video")
            failed_links.append({
                'url': line,
                'reason': 'Download Failed - Check if file is publicly accessible',
                'filename': filename,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue
        
        # Add delay to avoid rate limiting
        time.sleep(2)
        
        # Create release
        print(f"\n{'─'*80}")
        print("📦 STEP 2/3: Creating GitHub Release")
        print(f"{'─'*80}")
        
        release_tag = f"video-{safe_name}"
        release = create_unique_release(REPO_NAME, release_tag, GITHUB_TOKEN)
        
        if not release:
            print("✗ Failed to create release")
            try:
                os.remove(temp_path)
            except:
                pass
            failed_links.append({
                'url': line,
                'reason': 'GitHub Release Creation Failed',
                'filename': filename,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue
        
        # Add delay before upload
        time.sleep(2)
        
        # Upload to release
        print(f"\n{'─'*80}")
        print("☁️  STEP 3/3: Uploading to GitHub Release")
        print(f"{'─'*80}")
        
        github_url = upload_to_release(REPO_NAME, release['id'], temp_path, GITHUB_TOKEN)
        
        if github_url:
            github_links.append(github_url)
            print(f"\n✅ SUCCESS! Video {processed_count}/{total_drive_links} completed")
        else:
            print("✗ Upload failed")
            failed_links.append({
                'url': line,
                'reason': 'GitHub Upload Failed - File downloaded but upload error',
                'filename': filename,
                'release_tag': release_tag,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Cleanup
        try:
            os.remove(temp_path)
            print(f"🗑️  Cleaned up temporary file")
        except:
            pass
        
        print("=" * 80)
        time.sleep(1)  # Small delay between videos
    
    # Write results to drive.txt (only successful GitHub links)
    with open(DRIVE_FILE, 'w') as f:
        for link in github_links:
            f.write(link + '\n')
    
    # Write failed links to separate file with details
    if failed_links:
        failed_file = 'failed_drive_links.txt'
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("FAILED DRIVE LINKS - Retry These Links\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, failed in enumerate(failed_links, 1):
                f.write(f"\n{'─'*80}\n")
                f.write(f"Failed Link #{idx}\n")
                f.write(f"{'─'*80}\n")
                f.write(f"Drive URL: {failed['url']}\n")
                f.write(f"Reason: {failed['reason']}\n")
                
                if 'filename' in failed:
                    f.write(f"Filename: {failed['filename']}\n")
                if 'release_tag' in failed:
                    f.write(f"Release Tag: {failed['release_tag']}\n")
                    
                f.write(f"Timestamp: {failed['timestamp']}\n")
                f.write("\n" + "─"*80 + "\n")
            
            # Summary at the end
            f.write("\n" + "="*80 + "\n")
            f.write("SUMMARY\n")
            f.write("="*80 + "\n")
            f.write(f"Total Failed Links: {len(failed_links)}\n")
            
            # Group by reason
            reasons = {}
            for failed in failed_links:
                reason = failed['reason']
                reasons[reason] = reasons.get(reason, 0) + 1
            
            f.write("\nFailure Breakdown:\n")
            for reason, count in reasons.items():
                f.write(f"  • {reason}: {count}\n")
            
            f.write("\n" + "="*80 + "\n")
            f.write("\nTO RETRY: Copy the Drive URLs above and add them back to drive.txt\n")
            f.write("="*80 + "\n")
        
        print(f"\n📝 Failed links saved to: {failed_file}")
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 FINAL SUMMARY")
    print("=" * 80)
    
    successful = len(github_links) - (len([l for l in lines if 'github.com' in l]))
    
    print(f"✅ Total Drive links found:      {total_drive_links}")
    print(f"✅ Successfully converted:       {successful}")
    print(f"❌ Failed to convert:            {len(failed_links)}")
    print(f"📦 Total GitHub links in file:   {len(github_links)}")
    
    if failed_links:
        print(f"\n⚠️  {len(failed_links)} link(s) failed")
        print(f"📄 Check 'failed_drive_links.txt' for details and retry")
        print("\n💡 Common fixes:")
        print("   • Make sure Drive files are set to 'Anyone with the link can view'")
        print("   • Check if file IDs are correct")
        print("   • Verify GitHub token has proper permissions")
    else:
        print(f"\n🎉 All Drive links successfully converted to GitHub links!")
    
    print("=" * 80)

if __name__ == "__main__":
    process_drive_file()

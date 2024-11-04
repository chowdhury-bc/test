#!/bin/bash

# Set the bucket name
BUCKET_NAME="your-bucket-name"

# Get the list of files in the bucket sorted by LastModified in descending order
latest_file_info=$(aws s3api list-objects-v2 --bucket "$BUCKET_NAME" --query 'Contents | sort_by(@, &LastModified) | [-1]' --output json)

# Check if any file exists
if [ -z "$latest_file_info" ] || [ "$latest_file_info" == "null" ]; then
  echo "No files found in S3 bucket."
  exit 1
fi

# Extract the file key and LastModified timestamp using jq
latest_file_key=$(echo "$latest_file_info" | jq -r '.Key')
last_modified=$(echo "$latest_file_info" | jq -r '.LastModified')

# Output the filename and timestamp
echo "Latest File: $latest_file_key"
echo "Last Modified: $last_modified"




#!/bin/bash

# Check if bucket name is provided
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <bucket-name> [prefix]"
    echo "Example: $0 my-bucket path/to/files/"
    exit 1
fi

BUCKET="$1"
PREFIX="${2:-}"  # Optional prefix parameter, empty if not provided

# Get the latest file using list-objects-v2
if [ -z "$PREFIX" ]; then
    # List all files in bucket if no prefix
    LATEST_FILE=$(aws s3api list-objects-v2 \
        --bucket "$BUCKET" \
        --query 'sort_by(Contents, &LastModified)[-1].{Key: Key, LastModified: LastModified}' \
        --output json)
else
    # List files under specified prefix
    LATEST_FILE=$(aws s3api list-objects-v2 \
        --bucket "$BUCKET" \
        --prefix "$PREFIX" \
        --query 'sort_by(Contents, &LastModified)[-1].{Key: Key, LastModified: LastModified}' \
        --output json)
fi

# Check if any files were found
if [ "$LATEST_FILE" == "null" ]; then
    echo "No files found in bucket${PREFIX:+ under prefix '$PREFIX'}"
    exit 1
fi

# Extract and display the information
echo "Latest file details:"
echo "$LATEST_FILE" | jq -r '"File Key: \(.Key)\nUpload Timestamp: \(.LastModified)"'

# Optional: Format timestamp to your local timezone (uncomment if needed)
# TIMESTAMP=$(echo "$LATEST_FILE" | jq -r '.LastModified')
# echo "Local Time: $(date -d "$TIMESTAMP" '+%Y-%m-%d %H:%M:%S %Z')"

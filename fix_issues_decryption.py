"""
Fix script for issues.py - Add decryption to all customer_name fields
Run this to add decryption import and decrypt customer names in all endpoints
"""

import re

file_path = "core/routers/issues.py"

# Read the file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add import at the top if not exists
if "from core.utils.field_encryption import decrypt_field" not in content:
    # Find the last import line
    import_section = content.split('\n\n')[0]
    content = content.replace(import_section, import_section + "\nfrom core.utils.field_encryption import decrypt_field")

# Replace all occurrences of customer_name assignment
content = re.sub(
    r'"customer_name": issue\.customer\.full_name if issue\.customer else "Unknown"',
    r'"customer_name": decrypt_field(issue.customer.full_name) if issue.customer and issue.customer.full_name else "Unknown"',
    content
)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all customer_name fields in issues.py")

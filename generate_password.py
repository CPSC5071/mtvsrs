import csv
import os
import django
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mtvsrs.settings')
django.setup()

# Function to generate random passwords
def generate_random_passwords(length, count):
    passwords = [get_random_string(length) for _ in range(count)]
    hashed_passwords = [make_password(password) for password in passwords]
    return hashed_passwords

# Generate passwords
passwords_to_hash = generate_random_passwords(length=12, count=10)  # 10 passwords of 12 characters

# Write hashed passwords to a CSV file
with open('hashed_passwords.csv', 'w', newline='') as csvfile:
    password_writer = csv.writer(csvfile)
    password_writer.writerow(['password'])
    for pwd in passwords_to_hash:
        password_writer.writerow([pwd])

print("Hashed passwords have been written to hashed_passwords.csv")

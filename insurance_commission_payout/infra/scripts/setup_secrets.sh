#!/bin/bash

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-us-east-1}

echo "Commission Payout Pipeline - Secrets Setup"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

echo "Checking for required files..."

if [ ! -f "private.key" ]; then
    echo "Error: private.key not found"
    echo "Please generate PGP key pair first:"
    echo "  gpg --gen-key"
    echo "  gpg --export-secret-keys-armor 'Key ID' > private.key"
    exit 1
fi

if [ ! -f "passphrase.txt" ]; then
    echo "Error: passphrase.txt not found"
    echo "Please create passphrase.txt with your PGP passphrase"
    exit 1
fi

echo "Required files found"
echo ""

echo "Storing PGP private key in Secrets Manager..."

PRIVATE_KEY_SECRET="pgp-private-key-${ENVIRONMENT}"

aws secretsmanager create-secret \
    --name "$PRIVATE_KEY_SECRET" \
    --description "PGP private key for file decryption - $ENVIRONMENT" \
    --secret-string file://private.key \
    --region "$AWS_REGION" 2>/dev/null || \
aws secretsmanager update-secret \
    --secret-id "$PRIVATE_KEY_SECRET" \
    --secret-string file://private.key \
    --region "$AWS_REGION"

echo "Private key stored: $PRIVATE_KEY_SECRET"

echo "Storing PGP passphrase in Secrets Manager..."

PASSPHRASE_SECRET="pgp-passphrase-${ENVIRONMENT}"
PASSPHRASE=$(cat passphrase.txt)

aws secretsmanager create-secret \
    --name "$PASSPHRASE_SECRET" \
    --description "PGP passphrase for decryption - $ENVIRONMENT" \
    --secret-string "$PASSPHRASE" \
    --region "$AWS_REGION" 2>/dev/null || \
aws secretsmanager update-secret \
    --secret-id "$PASSPHRASE_SECRET" \
    --secret-string "$PASSPHRASE" \
    --region "$AWS_REGION"

echo "Passphrase stored: $PASSPHRASE_SECRET"

echo ""
echo "Verifying secrets..."

echo -n "Private key secret: "
if aws secretsmanager get-secret-value \
    --secret-id "$PRIVATE_KEY_SECRET" \
    --region "$AWS_REGION" \
    --query SecretString \
    --output text | head -1 | grep -q "BEGIN"; then
    echo "Valid"
else
    echo "Invalid"
    exit 1
fi

echo -n "Passphrase secret: "
if aws secretsmanager get-secret-value \
    --secret-id "$PASSPHRASE_SECRET" \
    --region "$AWS_REGION" \
    --query SecretString \
    --output text | grep -q .; then
    echo "Valid"
else
    echo "Invalid"
    exit 1
fi

echo ""
echo "Secrets setup complete!"
echo ""
echo "Add to your .env file:"
echo "  PGP_PRIVATE_KEY_SECRET=$PRIVATE_KEY_SECRET"
echo "  PGP_PASSPHRASE_SECRET=$PASSPHRASE_SECRET"

shred -u passphrase.txt 2>/dev/null || rm -f passphrase.txt
echo ""
echo "Securely deleted passphrase.txt"

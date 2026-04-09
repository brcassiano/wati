#!/bin/bash
# Usage: ./scripts/webhook_test.sh <message_id> <status> [error_code] [error_message]
# Examples:
#   ./scripts/webhook_test.sh abc-123 delivered
#   ./scripts/webhook_test.sh abc-123 read
#   ./scripts/webhook_test.sh abc-123 failed 470 "Number not in contact list"

MSG_ID="$1"
STATUS="$2"
ERROR_CODE="$3"
ERROR_MSG="$4"

if [ -z "$MSG_ID" ] || [ -z "$STATUS" ]; then
  echo "Usage: $0 <message_id> <status> [error_code] [error_message]"
  echo ""
  echo "Statuses: delivered, read, failed"
  echo ""
  echo "Health check:"
  curl -s http://localhost:8080/health
  echo ""
  exit 1
fi

JSON="{\"event_type\":\"message_status\",\"message_id\":\"$MSG_ID\",\"status\":\"$STATUS\""

if [ -n "$ERROR_CODE" ]; then
  JSON="$JSON,\"error_code\":\"$ERROR_CODE\""
fi
if [ -n "$ERROR_MSG" ]; then
  JSON="$JSON,\"error_message\":\"$ERROR_MSG\""
fi

JSON="$JSON}"

echo "POST /webhook/status"
echo "Payload: $JSON"
echo "---"
curl -s -X POST http://localhost:8080/webhook/status \
  -H "Content-Type: application/json" \
  --data-raw "$JSON"
echo ""

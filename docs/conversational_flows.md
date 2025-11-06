# Conversational Flows for Ingress Leaderboard Bot

This document outlines the exact conversational flows for the guided `/register` and `/submit` commands, including fallback messages for invalid input and examples for quick-submit syntax.

## `/register` Command Flow

### Initial State
- User types: `/register`
- Bot checks if user is already registered

### Flow 1: New User Registration

1. **Bot Prompt**: "Please send your agent codename."
   - State: Waiting for CODENAME
   - Expected User Input: A text string with the agent's codename

2. **User Input**: [Codename]
   - Bot validates:
     - Not empty
     - Not a command
   - If valid:
     - Bot stores codename in user_data
     - **Bot Prompt**: "Send your faction (ENL or RES)."
     - State: Waiting for FACTION
   - If invalid:
     - **Bot Prompt**: "Codename cannot be empty. Send your codename."
     - State: Still waiting for CODENAME

3. **User Input**: [Faction]
   - Bot validates:
     - Must be exactly "ENL" or "RES" (case-insensitive)
   - If valid:
     - Bot creates/updates agent record
     - **Bot Prompt**: "Registered [codename] ([faction])."
     - State: END
   - If invalid:
     - **Bot Prompt**: "Faction must be ENL or RES. Send your faction."
     - State: Still waiting for FACTION

### Flow 2: Already Registered User

1. **Bot Prompt**: "You are already registered as [codename] ([faction])."
   - State: END

### Fallback Scenarios

1. **User types `/cancel` at any point**:
   - **Bot Prompt**: "Registration cancelled."
   - State: END
   - User data cleared

2. **User types a command instead of expected input**:
   - Commands are filtered out, bot waits for valid text input

3. **Session timeout**:
   - If user doesn't respond within a reasonable time, conversation expires
   - User must restart with `/register`

## `/submit` Command Flow

### Current Implementation (Quick Submit)

1. **User types**: `/submit ap=12345; metric=678`
   - Bot parses the payload
   - Validates required "ap" field
   - Validates that "ap" is an integer
   - Validates user is registered

2. **Success Response**:
   - **Bot Prompt**: "Recorded [ap] AP for [codename]."
   - Submission is recorded in database
   - If autodelete is enabled, message is scheduled for deletion

3. **Error Responses**:
   - No payload: "Usage: /submit ap=12345; metric=678"
   - Invalid format: "Entries must be provided as key=value pairs"
   - Missing AP: "Missing ap value"
   - Invalid AP: "ap must be an integer"
   - Not registered: "Register first with /register."

### Proposed Guided Submit Flow

To enhance user experience, we can implement a guided flow similar to registration:

1. **User types**: `/submit`
   - Bot checks if user is registered
   - If not registered: "Register first with /register."
   - If registered: **Bot Prompt**: "Please enter your AP amount."

2. **User Input**: [AP amount]
   - Bot validates:
     - Must be a valid integer
   - If valid:
     - Bot stores AP in user_data
     - **Bot Prompt**: "Enter any additional metrics (key=value pairs, separated by semicolons), or send 'skip' to continue."
   - If invalid:
     - **Bot Prompt**: "AP must be a valid integer. Please enter your AP amount."

3. **User Input**: [Metrics or "skip"]
   - If "skip":
     - Bot records submission with just AP
     - **Bot Prompt**: "Recorded [ap] AP for [codename]."
     - State: END
   - If metrics provided:
     - Bot validates format (key=value pairs)
     - If valid:
       - Bot records submission with AP and metrics
       - **Bot Prompt**: "Recorded [ap] AP for [codename]."
       - State: END
     - If invalid:
       - **Bot Prompt**: "Invalid format. Use key=value pairs separated by semicolons, or send 'skip' to continue."

## Quick-Submit Syntax Examples

### Basic AP Submission
```
/submit ap=15000
```

### AP with Multiple Metrics
```
/submit ap=15000; mu=500; links=100; fields=25
```

### AP with Decimal Metrics
```
/submit ap=15000; xm_ratio=0.85; efficiency=92.5
```

### Multi-line Submission
```
/submit ap=15000
mu=500
links=100
fields=25
```

### Using Double Spaces as Separators
```
/submit ap=15000  mu=500  links=100  fields=25
```

## Error Handling and Fallback Messages

### Common Error Messages

1. **Registration Errors**:
   - "Codename cannot be empty. Send your codename."
   - "Faction must be ENL or RES. Send your faction."
   - "Codename missing. Restart with /register."
   - "Registration cancelled."

2. **Submission Errors**:
   - "Register first with /register."
   - "Usage: /submit ap=12345; metric=678"
   - "Entries must be provided as key=value pairs"
   - "Missing ap value"
   - "ap must be an integer"
   - "Invalid entry"

3. **General Errors**:
   - "An unexpected error occurred. Please try again later."

### Input Validation Rules

1. **Codename**:
   - Required field
   - Cannot be empty
   - Maximum 64 characters (database constraint)
   - Can contain any characters except commands

2. **Faction**:
   - Required field
   - Must be exactly "ENL" or "RES" (case-insensitive)

3. **AP**:
   - Required field for submissions
   - Must be a valid integer
   - No explicit range, but should be reasonable for Ingress gameplay

4. **Metrics**:
   - Optional field
   - Key-value pairs separated by semicolons, newlines, or double spaces
   - Keys are converted to lowercase
   - Values can be integers, floats, or strings
   - Empty keys or values are rejected

## Implementation Notes

1. **State Management**:
   - Registration uses ConversationHandler with states: CODENAME, FACTION
   - Current submit implementation is stateless (one-shot)
   - Guided submit would need additional states

2. **Data Storage**:
   - User data is stored in context.user_data during conversations
   - Cleared after successful registration or cancellation

3. **Database Operations**:
   - All database operations use session_scope for proper connection management
   - Agent records are created or updated during registration
   - Submission records are created with agent_id, ap, and metrics

4. **Auto-delete Feature**:
   - If enabled, submission confirmation messages are automatically deleted
   - Both the user's original message and bot's reply are deleted
   - Delay is configurable via settings
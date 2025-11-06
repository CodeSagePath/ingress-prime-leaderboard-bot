# Ingress Prime Leaderboard Bot - QA Checklist

This document provides a comprehensive QA checklist for testing the main features of the Ingress Prime Leaderboard Bot.

## Table of Contents
1. [Register Feature](#register-feature)
2. [Submit Feature](#submit-feature)
3. [Group Submit + Autodelete Feature](#group-submit--autodelete-feature)
4. [Leaderboard Caching Feature](#leaderboard-caching-feature)
5. [Verification Queue Feature](#verification-queue-feature)
6. [Admin Commands](#admin-commands)

---

## 1. Register Feature

### Overview
The register feature allows users to register as agents with their codename and faction (ENL or RES). This is implemented as a conversation handler in [`bot/main.py`](bot/main.py:70-118).

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Database connection is established
- Redis connection is established (for background jobs)

### Test Scenarios

#### Positive Cases
1. **Successful Registration Flow**
   - User sends `/register` command
   - User provides a valid codename
   - User provides a valid faction (ENL or RES)
   - Expected: User receives confirmation message with codename and faction
   - Expected: Agent data is persisted in the database

2. **Re-registration with Same Telegram ID**
   - Already registered user sends `/register` command
   - Expected: User receives message indicating they are already registered
   - Expected: Existing agent data is updated with new codename and faction

3. **Faction Case Insensitivity**
   - User sends `/register` command
   - User provides a valid codename
   - User provides faction in lowercase (enl/res) or mixed case (EnL/ReS)
   - Expected: Faction is stored in uppercase in the database
   - Expected: User receives confirmation message with uppercase faction

#### Negative Cases
1. **Empty Codename**
   - User sends `/register` command
   - User provides empty codename
   - Expected: User receives error message asking for a valid codename
   - Expected: Registration process continues until valid codename is provided

2. **Invalid Faction**
   - User sends `/register` command
   - User provides a valid codename
   - User provides invalid faction (not ENL or RES)
   - Expected: User receives error message asking for valid faction
   - Expected: Registration process continues until valid faction is provided

3. **Registration Cancellation**
   - User sends `/register` command
   - User sends `/cancel` command during registration
   - Expected: User receives cancellation message
   - Expected: Registration process is terminated
   - Expected: No data is stored in the database

### Expected Outcomes
- Successful registration stores agent data in the `agents` table with:
  - Valid telegram_id
  - Valid codename (max 64 characters)
  - Valid faction (ENL or RES)
  - Timestamp of creation
- Error messages are clear and guide users to correct input
- Registration conversation state is properly managed

### Edge Cases to Consider
1. **Very Long Codename**
   - User provides codename longer than 64 characters
   - Expected: Database should truncate or reject based on model constraints

2. **Special Characters in Codename**
   - User provides codename with special characters
   - Expected: Codename is accepted as long as it's not empty

3. **Network Interruption During Registration**
   - Network connection is lost during registration process
   - Expected: Registration process should resume or restart cleanly when connection is restored

4. **Multiple Registration Attempts**
   - User starts multiple registration conversations simultaneously
   - Expected: Each conversation should be handled independently

### Performance Considerations
- Registration response time should be < 2 seconds under normal conditions
- Database queries should be optimized to prevent delays
- Concurrent registrations should not cause deadlocks or race conditions

### Security Considerations
- Telegram ID should be validated to prevent spoofing
- Codename should be sanitized to prevent SQL injection
- Faction input should be strictly validated to only allow ENL or RES
- User data should not be exposed to other users

---

## 2. Submit Feature

### Overview
The submit feature allows registered users to submit their AP (Access Points) and other metrics. This is implemented in [`bot/main.py`](bot/main.py:128-162) with parsing logic in [`parse_submission()`](bot/main.py:30-61).

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Database connection is established
- Redis connection is established (for autodelete feature)
- User is registered as an agent

### Test Scenarios

#### Positive Cases
1. **Valid AP Submission**
   - Registered user sends `/submit ap=12345`
   - Expected: User receives confirmation message with AP value and codename
   - Expected: Submission data is persisted in the database

2. **AP with Multiple Metrics**
   - Registered user sends `/submit ap=12345; hacks=17; distance=12.5; note=First run`
   - Expected: User receives confirmation message
   - Expected: All metrics are parsed and stored correctly in the database

3. **Different Submission Formats**
   - Registered user sends `/submit ap=12345 hacks=17 distance=12.5` (space-separated)
   - Registered user sends `/submit ap=12345\nhacks=17\ndistance=12.5` (newline-separated)
   - Expected: All formats are parsed correctly
   - Expected: Submission data is persisted in the database

#### Negative Cases
1. **Missing AP Value**
   - Registered user sends `/submit hacks=17`
   - Expected: User receives error message about missing AP value
   - Expected: No data is stored in the database

2. **Invalid AP Format**
   - Registered user sends `/submit ap=not_a_number`
   - Expected: User receives error message about AP being an integer
   - Expected: No data is stored in the database

3. **Unregistered User Submission**
   - Unregistered user sends `/submit ap=12345`
   - Expected: User receives message to register first
   - Expected: No data is stored in the database

4. **Empty Submission**
   - Registered user sends `/submit` without any data
   - Expected: User receives usage instructions
   - Expected: No data is stored in the database

### Expected Outcomes
- Successful submission stores data in the `submissions` table with:
  - Valid agent_id referencing the agent
  - Valid AP value as integer
  - Metrics stored as JSON
  - Timestamp of submission
- Confirmation message includes the AP value and agent codename
- Error messages are clear and guide users to correct input format

### Edge Cases to Consider
1. **Very Large AP Values**
   - User submits extremely large AP values
   - Expected: System should handle within database integer constraints

2. **Negative AP Values**
   - User submits negative AP values
   - Expected: System should accept or reject based on business rules

3. **Special Characters in Metrics**
   - User submits metrics with special characters
   - Expected: System should handle special characters appropriately

4. **Malformed Key-Value Pairs**
   - User submits malformed entries like `ap12345` (missing equals)
   - Expected: System should reject with appropriate error message

### Performance Considerations
- Submission processing time should be < 2 seconds under normal conditions
- Database writes should be optimized to prevent delays
- Concurrent submissions should not cause deadlocks or race conditions

### Security Considerations
- Input should be sanitized to prevent injection attacks
- Metrics should be validated to ensure proper data types
- Users should only be able to submit data for themselves
- Submission data should not be exposed to other users

---

## 3. Group Submit + Autodelete Feature

### Overview
The group submit and autodelete feature allows users to submit AP in group chats, with automatic deletion of both the user's submission message and the bot's confirmation message after a configured delay. This is implemented in [`bot/main.py`](bot/main.py:154-162) and [`bot/jobs/deletion.py`](bot/jobs/deletion.py).

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Database connection is established
- Redis connection is established
- Bot has been added to a group chat
- Bot has admin permissions in the group chat
- Autodelete feature is enabled in configuration

### Test Scenarios

#### Positive Cases
1. **Successful Submission in Group with Autodelete**
   - Registered user sends `/submit ap=12345` in a group chat
   - Expected: Bot replies with confirmation message
   - Expected: Both user's message and bot's reply are deleted after the configured delay
   - Expected: Submission data is persisted in the database

2. **Autodelete with Custom Delay**
   - Configuration has custom autodelete delay (e.g., 60 seconds)
   - Registered user sends `/submit ap=12345` in a group chat
   - Expected: Messages are deleted after the custom delay

3. **Autodelete Job Scheduling**
   - Registered user sends multiple submissions in a group chat
   - Expected: Each submission schedules a separate deletion job
   - Expected: All jobs are executed at their scheduled times

#### Negative Cases
1. **Bot Lacks Delete Permissions**
   - Bot does not have delete permissions in the group chat
   - Registered user sends `/submit ap=12345`
   - Expected: Bot replies with confirmation message
   - Expected: Messages are not deleted
   - Expected: Warning is logged about missing permissions

2. **Autodelete Feature Disabled**
   - Autodelete is disabled in configuration
   - Registered user sends `/submit ap=12345` in a group chat
   - Expected: Bot replies with confirmation message
   - Expected: Messages are not deleted
   - Expected: No deletion jobs are scheduled

3. **Redis Connection Failure**
   - Redis connection is not available
   - Registered user sends `/submit ap=12345` in a group chat
   - Expected: Bot replies with confirmation message
   - Expected: Messages are not deleted
   - Expected: Error is logged about Redis connection

### Expected Outcomes
- Deletion jobs are properly scheduled in Redis queue
- Messages are deleted at the scheduled time
- Bot permissions are verified before attempting deletion
- Errors during deletion are properly logged
- Submission data is stored regardless of deletion success

### Edge Cases to Consider
1. **Message Already Deleted**
   - User manually deletes their message before scheduled deletion
   - Expected: Bot should handle gracefully without errors

2. **Bot Removed from Group**
   - Bot is removed from the group after scheduling deletion
   - Expected: Deletion job should fail gracefully with appropriate logging

3. **Very Long Autodelete Delay**
   - Configuration has very long autodelete delay (e.g., 24 hours)
   - Expected: Deletion job should still execute at the scheduled time

4. **Multiple Submissions in Quick Succession**
   - User sends multiple submissions in quick succession
   - Expected: Each submission should schedule its own deletion job
   - Expected: All jobs should execute at their scheduled times

### Performance Considerations
- Deletion job scheduling should not delay confirmation message
- Redis queue should handle multiple deletion jobs efficiently
- Deletion operations should not impact bot's responsiveness
- Long deletion delays should not cause memory leaks

### Security Considerations
- Bot should verify its permissions before attempting deletion
- Deletion jobs should only be scheduled for the specific messages involved
- Sensitive job data should be properly secured in Redis
- Error messages should not expose sensitive information

---

## 4. Leaderboard Caching Feature

### Overview
The leaderboard caching feature periodically calculates and caches leaderboard data to improve performance. This is implemented in [`bot/jobs/leaderboard_worker.py`](bot/jobs/leaderboard_worker.py) and [`bot/services/leaderboard.py`](bot/services/leaderboard.py).

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Database connection is established
- Redis connection is established
- Leaderboard worker process is running
- Database contains agent and submission data

### Test Scenarios

#### Positive Cases
1. **Leaderboard Command with Data**
   - User sends `/leaderboard` command
   - Database contains submission data
   - Expected: Bot replies with formatted leaderboard showing top agents
   - Expected: Leaderboard shows agent codename, faction, and total AP

2. **Leaderboard Command with No Data**
   - User sends `/leaderboard` command
   - Database contains no submission data
   - Expected: Bot replies with message indicating no submissions yet

3. **Leaderboard Size Configuration**
   - Configuration has custom leaderboard size (e.g., 15)
   - User sends `/leaderboard` command
   - Expected: Bot replies with leaderboard showing the configured number of agents

4. **Background Cache Update**
   - Leaderboard worker process is running
   - Expected: Cache is updated according to the configured schedule
   - Expected: Database contains updated cache data

#### Negative Cases
1. **Database Connection Failure**
   - Database connection is not available
   - User sends `/leaderboard` command
   - Expected: Bot replies with error message or appropriate fallback
   - Expected: Error is logged appropriately

2. **Invalid Leaderboard Size Configuration**
   - Configuration has invalid leaderboard size (e.g., 0 or negative)
   - User sends `/leaderboard` command
   - Expected: Bot should handle gracefully with default or appropriate error

3. **Cache Worker Process Failure**
   - Leaderboard worker process fails or stops
   - Expected: System should detect and log the failure
   - Expected: Leaderboard command should still work with direct database queries

### Expected Outcomes
- Leaderboard data is calculated correctly based on submission data
- Leaderboard is formatted properly with agent rankings
- Cache is updated according to the configured schedule
- Leaderboard command responds with cached data when available
- Fallback to direct database queries when cache is not available

### Edge Cases to Consider
1. **Tie in AP Values**
   - Multiple agents have the same total AP
   - Expected: Leaderboard should break ties consistently (e.g., by codename)

2. **Very Large Number of Agents**
   - Database contains submissions from many agents
   - Expected: Leaderboard calculation should complete in reasonable time
   - Expected: Leaderboard command should respond quickly

3. **Agents with No Submissions**
   - Database contains agents with no submissions
   - Expected: These agents should not appear in the leaderboard
   - Expected: Leaderboard should only show agents with submissions

4. **Changing Leaderboard Size**
   - Leaderboard size configuration is changed
   - Expected: Next leaderboard command should reflect the new size
   - Expected: Cache should be updated with the new size

### Performance Considerations
- Leaderboard calculation should complete efficiently even with large datasets
- Cache updates should not impact bot's responsiveness
- Leaderboard command should respond quickly (< 2 seconds)
- Database queries should be optimized for performance

### Security Considerations
- Leaderboard data should not expose sensitive information
- Cache data should be properly secured in Redis
- Database queries should be protected against injection attacks
- Error messages should not expose sensitive system information

---

## 5. Verification Queue Feature

### Overview
The verification queue feature uses Redis Queue to process background jobs asynchronously. This is implemented in [`bot/main.py`](bot/main.py:201-202) and used by various features like message deletion and leaderboard caching.

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Redis connection is established
- Redis Queue is properly configured
- Worker processes are running

### Test Scenarios

#### Positive Cases
1. **Job Enqueueing and Processing**
   - System enqueues a job (e.g., message deletion)
   - Worker process is running
   - Expected: Job is properly added to the queue
   - Expected: Worker picks up and processes the job
   - Expected: Job completes successfully

2. **Job Retry on Failure**
   - Job fails during processing
   - Expected: System should retry the job according to configuration
   - Expected: Failure should be logged appropriately

3. **Multiple Job Types**
   - System enqueues different types of jobs (e.g., deletion, leaderboard update)
   - Expected: All job types are processed correctly
   - Expected: Jobs don't interfere with each other

#### Negative Cases
1. **Redis Connection Failure**
   - Redis connection is not available
   - System attempts to enqueue a job
   - Expected: System should handle gracefully with appropriate error handling
   - Expected: Error should be logged appropriately

2. **Worker Process Failure**
   - Worker process fails or stops
   - Jobs are enqueued
   - Expected: Jobs should remain in queue until worker is available
   - Expected: System should detect and log worker failure

3. **Job Processing Timeout**
   - Job takes longer than expected timeout
   - Expected: System should handle timeout appropriately
   - Expected: Job should be marked as failed or retried

### Expected Outcomes
- Jobs are properly enqueued with correct parameters
- Workers process jobs in the order they were received (FIFO)
- Failed jobs are retried according to configuration
- Job status and results are properly tracked
- System performance is not impacted by job processing

### Edge Cases to Consider
1. **Queue Overflow**
   - Very large number of jobs are enqueued quickly
   - Expected: System should handle gracefully without crashing
   - Expected: Jobs should be processed in order

2. **Worker Overload**
   - More jobs are enqueued than workers can handle
   - Expected: System should queue jobs appropriately
   - Expected: Workers should process jobs as they become available

3. **Job with Invalid Parameters**
   - Job is enqueued with invalid or missing parameters
   - Expected: Worker should handle gracefully with appropriate error handling
   - Expected: Error should be logged appropriately

4. **Redis Memory Limit**
   - Redis approaches memory limit
   - Expected: System should handle gracefully with appropriate error handling
   - Expected: Critical jobs should still be processed

### Performance Considerations
- Job enqueueing should be fast and not impact bot responsiveness
- Worker processing should be efficient and not cause bottlenecks
- Redis memory usage should be monitored and managed
- System should scale to handle expected job volume

### Security Considerations
- Job data should be properly secured in Redis
- Sensitive information should not be stored in job parameters
- Job processing should not introduce security vulnerabilities
- Error messages should not expose sensitive information

---

## 6. Admin Commands

### Overview
Currently, no admin commands are implemented in the bot. This section is included for future reference when admin functionality is added.

### Pre-conditions for Testing
- Bot is running and accessible via Telegram
- Database connection is established
- Redis connection is established
- Admin users are properly identified and authorized

### Test Scenarios
*(Note: These scenarios are for future implementation)*

#### Positive Cases
1. **Admin Authentication**
   - Admin user sends admin command
   - Expected: Command is executed successfully
   - Expected: Appropriate response is returned

2. **User Management**
   - Admin user executes user management command
   - Expected: User data is modified as requested
   - Expected: Confirmation is returned to admin

3. **System Status**
   - Admin user requests system status
   - Expected: System status information is returned
   - Expected: Information includes database, Redis, and worker status

#### Negative Cases
1. **Unauthorized Admin Access**
   - Non-admin user attempts to execute admin command
   - Expected: Command is rejected
   - Expected: Appropriate warning is returned

2. **Invalid Admin Command**
   - Admin user sends invalid admin command
   - Expected: Error message is returned
   - Expected: System remains stable

### Expected Outcomes
*(Note: These outcomes are for future implementation)*
- Admin commands are properly authenticated and authorized
- Admin operations are executed correctly
- Appropriate responses are returned for admin commands
- System security is maintained

### Edge Cases to Consider
*(Note: These cases are for future implementation)*
1. **Admin Command During High Load**
   - Admin command is executed during system high load
   - Expected: Command should still execute correctly
   - Expected: System performance should not be significantly impacted

2. **Conflicting Admin Commands**
   - Multiple admin commands are executed simultaneously
   - Expected: Commands should not interfere with each other
   - Expected: System should handle conflicts appropriately

### Performance Considerations
*(Note: These considerations are for future implementation)*
- Admin commands should not significantly impact system performance
- Admin operations should be efficient even with large datasets
- System should remain responsive during admin operations

### Security Considerations
*(Note: These considerations are for future implementation)*
- Admin commands should be properly authenticated and authorized
- Sensitive operations should require additional confirmation
- Admin actions should be logged for audit purposes
- Error messages should not expose sensitive system information
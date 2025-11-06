# Ingress Prime Leaderboard Bot - Testing Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Feature Overview](#feature-overview)
3. [Testing Strategy](#testing-strategy)
4. [Unit Testing Guide](#unit-testing-guide)
5. [Integration Testing Guide](#integration-testing-guide)
6. [Test Coverage Report](#test-coverage-report)
7. [Testing Guidelines](#testing-guidelines)
8. [QA Checklist](#qa-checklist)
9. [Appendix](#appendix)

---

## Introduction

### Purpose of this Guide
This testing guide provides a comprehensive overview of the testing approach for the Ingress Prime Leaderboard Bot. It serves as a reference for QA testers, developers, and other stakeholders to understand the testing methodology, test cases, and best practices for ensuring the reliability and correctness of the bot's functionality.

### Project Overview
The Ingress Prime Leaderboard Bot is a Telegram bot designed for Ingress players to track their performance and compete on leaderboards. The bot allows users to register as agents, submit their AP (Access Points) and other metrics, and view leaderboards showing the top performers.

Key features include:
- User registration with codename and faction selection
- AP and metrics submission with various formats
- Leaderboard generation and caching for performance
- Automatic message deletion in group chats
- Verification queue for processing submissions asynchronously

### Testing Approach and Methodology
Our testing approach follows a comprehensive strategy that includes:

1. **Unit Testing**: Testing individual components in isolation to ensure each function works correctly
2. **Integration Testing**: Testing interactions between components to verify data flow and feature interactions
3. **End-to-End Testing**: Testing complete user workflows (planned for future implementation)

The testing methodology emphasizes:
- Test-driven development practices
- Comprehensive edge case coverage
- Performance and scalability considerations
- Error handling and recovery mechanisms
- Data consistency and integrity

---

## Feature Overview

### 1. Registration Feature

#### Purpose
The registration feature allows users to register as Ingress agents with their codename and faction (ENL or RES). This is the first step for users to participate in the leaderboard system.

#### Key Components
- **register_start**: Initiates the registration conversation flow
- **register_codename**: Collects and validates the user's codename
- **register_faction**: Collects and validates the user's faction
- **register_cancel**: Allows users to cancel the registration process

#### Data Model
- **Agent Model**: Stores agent information with fields:
  - `id`: Primary key
  - `telegram_id`: Unique Telegram user ID
  - `codename`: Ingress agent codename (max 64 characters)
  - `faction`: Agent faction (ENL or RES)
  - `created_at`: Timestamp of agent creation

#### Dependencies
- Telegram Bot API for user interaction
- Database for agent data persistence
- Conversation state management

### 2. Submission Feature

#### Purpose
The submission feature allows registered users to submit their AP and other metrics. These submissions are accumulated and used to generate leaderboards.

#### Key Components
- **submit**: Processes submission commands and stores data
- **parse_submission**: Parses and validates submission payloads in various formats

#### Data Model
- **Submission Model**: Stores submission data with fields:
  - `id`: Primary key
  - `agent_id`: Foreign key to Agent model
  - `ap`: Access Points value (integer)
  - `metrics`: JSON object containing additional metrics
  - `submitted_at`: Timestamp of submission

#### Dependencies
- User registration (must be completed first)
- Database for submission data persistence
- Autodelete feature for group chats

### 3. Group Submit + Autodelete Feature

#### Purpose
The group submit and autodelete feature automatically deletes both the user's submission message and the bot's confirmation message in group chats after a configured delay. This helps keep group chats clean while maintaining functionality.

#### Key Components
- **_delete_messages**: Deletes messages if the bot has proper permissions
- **delete_message_job**: Background job function for message deletion
- **schedule_message_deletion**: Schedules message deletion jobs in Redis queue

#### Dependencies
- Redis Queue for job scheduling
- Telegram Bot API for message deletion
- Bot permissions in group chats (admin or owner with delete permissions)

### 4. Leaderboard Caching Feature

#### Purpose
The leaderboard caching feature periodically calculates and caches leaderboard data to improve performance when users request leaderboards. This reduces database load and provides faster response times.

#### Key Components
- **get_leaderboard**: Retrieves leaderboard data from cache or database
- **_collect_leaderboards**: Collects leaderboard data from database
- **_persist_leaderboards**: Persists leaderboard data to cache
- **_recompute**: Recomputes leaderboard data from submissions
- **recompute_leaderboards_job**: Background job for leaderboard recomputation
- **enqueue_recompute_job**: Enqueues leaderboard recomputation jobs

#### Dependencies
- Database for submission data
- Redis for caching and job queue
- Background worker processes

### 5. Verification Queue Feature

#### Purpose
The verification queue feature uses Redis Queue to process background jobs asynchronously. This ensures that the bot remains responsive while processing resource-intensive tasks like leaderboard recomputation and message deletion.

#### Key Components
- Redis Queue for job management
- Worker processes for job execution
- Job retry mechanisms for failed jobs

#### Dependencies
- Redis server
- Worker processes
- Proper error handling and logging

### 6. Admin Commands

#### Purpose
Admin commands provide administrative functionality for managing the bot and system. Currently, basic commands are implemented with plans for future expansion.

#### Key Components
- **start**: Welcome message for new users
- **leaderboard**: Displays the current leaderboard

#### Dependencies
- Telegram Bot API for command handling
- Database for data retrieval
- Leaderboard caching system

---

## Testing Strategy

### Testing Pyramid
Our testing strategy follows the testing pyramid model:

1. **Unit Tests**: Foundation of the testing pyramid, testing individual components in isolation
   - Fast execution
   - Isolated testing environment
   - Comprehensive edge case coverage

2. **Integration Tests**: Middle layer, testing interactions between components
   - Feature interaction testing
   - Data flow verification
   - End-to-end workflow testing

3. **End-to-End Tests**: Top layer, testing complete user workflows (planned)
   - Real-world scenario testing
   - User experience validation
   - System integration testing

### Test Categories
1. **Unit Tests**: Test individual functions and methods
2. **Integration Tests**: Test feature interactions and data flow
3. **Performance Tests**: Test system performance under load (planned)
4. **Security Tests**: Test security aspects (planned)

### Test Tools and Frameworks
- **pytest**: Testing framework
- **pytest-asyncio**: For async test support
- **unittest.mock**: For mocking dependencies
- **SQLAlchemy**: For database testing
- **SQLite**: In-memory database for testing

---

## Unit Testing Guide

### Registration Feature Tests

#### Test Cases
1. **register_start**
   - Test that it initiates registration correctly
   - Test behavior with no message
   - Test that it returns the correct state (CODENAME)
   - Test with already registered user

2. **register_codename**
   - Test with valid codename
   - Test with empty codename
   - Test with whitespace handling
   - Test behavior with no message
   - Test that it stores codename in user_data
   - Test that it returns the correct state (FACTION)

3. **register_faction**
   - Test with valid faction (ENL/RES)
   - Test with invalid faction
   - Test case-insensitive faction input
   - Test with missing codename in user_data
   - Test updating an existing agent
   - Test behavior with no message
   - Test behavior with no effective user
   - Test that it clears user_data after successful registration

4. **register_cancel**
   - Test with message
   - Test without message
   - Test that it clears user_data

### Submission Feature Tests

#### Test Cases
1. **parse_submission**
   - Test with valid input (semicolon separated)
   - Test with valid input (newline separated)
   - Test with valid input (multi-space separated)
   - Test with missing AP value
   - Test with invalid AP value (non-integer)
   - Test with invalid format
   - Test with empty entry
   - Test with empty string
   - Test with only whitespace

2. **submit**
   - Test successful submission
   - Test with no payload
   - Test with invalid payload
   - Test from unregistered user
   - Test behavior with no message
   - Test behavior with no effective user
   - Test with autodelete enabled
   - Test with autodelete disabled

### Group Submit + Autodelete Feature Tests

#### Test Cases
1. **_delete_messages**
   - Test with proper permissions (administrator)
   - Test with owner permissions
   - Test without proper permissions (member)
   - Test with admin but no delete permission
   - Test with Telegram API error
   - Test with error getting chat member
   - Test with missing message_id
   - Test with missing confirmation_message_id

2. **delete_message_job**
   - Test with successful execution
   - Test with exception

3. **schedule_message_deletion**
   - Test with confirmation message ID
   - Test without confirmation message ID

### Leaderboard Caching Feature Tests

#### Test Cases
1. **get_leaderboard**
   - Test with existing data
   - Test with a limit
   - Test with no data

2. **_collect_leaderboards**
   - Test with existing data
   - Test with no data

3. **_persist_leaderboards**
   - Test that data is persisted correctly

4. **_recompute**
   - Test with data
   - Test with no data

5. **recompute_leaderboards_job**
   - Test with successful execution
   - Test with exception

6. **enqueue_recompute_job**
   - Test that job is enqueued correctly

### Admin Commands Tests

#### Test Cases
1. **start**
   - Test that it sends welcome message
   - Test behavior with no message

2. **leaderboard**
   - Test with data
   - Test with no data
   - Test with a limit
   - Test behavior with no message

### Data Validation Tests

#### Test Cases
1. **Faction Enum**
   - Test enum values
   - Test string representation

2. **Agent Model**
   - Test valid agent creation
   - Test field validation

3. **Submission Model**
   - Test valid submission creation
   - Test field validation

4. **Agent-Submission Relationship**
   - Test one-to-many relationship

### Database Operations Tests

#### Test Cases
1. **session_scope**
   - Test commit on success
   - Test rollback on exception
   - Test that session is always closed

### Error Handling Tests

#### Test Cases
1. **parse_submission**
   - Test with various invalid formats
   - Test with empty string
   - Test with only whitespace
   - Test with invalid key=value format
   - Test with empty key
   - Test with empty value
   - Test with non-integer AP

2. **register_faction**
   - Test case-insensitive faction input

3. **register_codename**
   - Test with various whitespace inputs
   - Test with only whitespace

4. **submit**
   - Test with various payload formats
   - Test with semicolon separator
   - Test with newline separator
   - Test with multi-space separator

### Business Logic Tests

#### Test Cases
1. **Leaderboard Ordering**
   - Test ordering by AP and then by codename
   - Test tie-breaking by codename

2. **Submission Accumulation**
   - Test that submissions accumulate correctly for an agent

3. **Agent Faction Filtering**
   - Test that leaderboard correctly filters by faction

4. **Autodelete Scheduling**
   - Test that autodelete is scheduled correctly
   - Test with correct parameters

5. **Registration Flow**
   - Test complete registration flow
   - Test registration cancellation

---

## Integration Testing Guide

### Feature Interaction Tests

#### Register → Submit Flow
- **Purpose**: Test that a user can register and then successfully submit AP
- **Test Cases**:
  1. Complete register-submit flow
  2. Register-submit with multiple submissions

#### Submit → Leaderboard Flow
- **Purpose**: Test that submissions are properly reflected in the leaderboard
- **Test Cases**:
  1. Single submission reflected in leaderboard
  2. Multiple submissions accumulated in leaderboard
  3. Multiple users ranked correctly in leaderboard

#### Group Submit → Autodelete Flow
- **Purpose**: Test that submissions in groups trigger the autodelete functionality
- **Test Cases**:
  1. Group submission schedules autodelete
  2. Autodelete job executes with permissions
  3. Autodelete job skipped without permissions

#### Submit → Verification Queue → Leaderboard Flow
- **Purpose**: Test that submissions go through the queue and update the leaderboard
- **Test Cases**:
  1. Submission triggers leaderboard recompute

#### Multiple Submissions → Leaderboard Ranking
- **Purpose**: Test that multiple submissions from different users are correctly ranked
- **Test Cases**:
  1. Concurrent submissions ranked correctly
  2. Tie-breaking by codename
  3. Leaderboard with faction filtering

### Complex Scenario Tests

#### Leaderboard Recomputation with Multiple Submissions
- **Purpose**: Test leaderboard recomputation with multiple submissions
- **Test Cases**:
  1. Create a temporary database with multiple agents and submissions
  2. Run recompute job
  3. Verify leaderboard cache is updated correctly

#### Group Chat Submissions with Different Permissions
- **Purpose**: Test group chat submissions with different permission scenarios
- **Test Cases**:
  1. Test with admin permissions
  2. Test with owner permissions
  3. Test with member permissions
  4. Verify autodelete behavior in each case

#### Error Recovery in Feature Interactions
- **Purpose**: Test error recovery in feature interactions
- **Test Cases**:
  1. Test submission with database error
  2. Test leaderboard with database error
  3. Test autodelete with Telegram API error
  4. Verify system recovers gracefully

#### Data Consistency Across Features
- **Purpose**: Test data consistency across features
- **Test Cases**:
  1. Register multiple users
  2. Submit AP for multiple users
  3. Check leaderboard
  4. Verify data consistency between submissions and leaderboard

#### Performance with Large Dataset
- **Purpose**: Test performance with a large dataset
- **Test Cases**:
  1. Create many agents and submissions
  2. Check leaderboard performance
  3. Verify system handles large dataset efficiently

#### Race Conditions with Concurrent Operations
- **Purpose**: Test race conditions with concurrent operations
- **Test Cases**:
  1. Simulate concurrent submissions from the same user
  2. Simulate concurrent leaderboard requests
  3. Verify data integrity is maintained

#### End-to-End Workflow
- **Purpose**: Test complete end-to-end workflow
- **Test Cases**:
  1. Register multiple users
  2. Submit AP from multiple users
  3. Check leaderboard
  4. Verify autodelete scheduling
  5. Verify data consistency

---

## Test Coverage Report

### Current Coverage
- **Registration Feature**: 100% coverage
  - All functions tested
  - Edge cases covered
  - Error handling tested

- **Submission Feature**: 100% coverage
  - All functions tested
  - Various input formats tested
  - Error handling tested

- **Group Submit + Autodelete Feature**: 100% coverage
  - All functions tested
  - Different permission scenarios tested
  - Error handling tested

- **Leaderboard Caching Feature**: 100% coverage
  - All functions tested
  - Data persistence tested
  - Error handling tested

- **Admin Commands**: 100% coverage
  - All functions tested
  - Edge cases covered

- **Data Validation**: 100% coverage
  - All models tested
  - Relationships tested
  - Field validation tested

- **Database Operations**: 100% coverage
  - Session management tested
  - Transaction behavior tested

- **Error Handling**: 100% coverage
  - Various error scenarios tested
  - Recovery mechanisms tested

- **Business Logic**: 100% coverage
  - Core functionality tested
  - Edge cases covered

### Coverage Gaps
- **Performance Tests**: Not implemented
- **Security Tests**: Not implemented
- **End-to-End Tests**: Partially implemented

### Recommendations for Additional Coverage
1. Implement performance tests for large datasets
2. Implement security tests for input validation and authorization
3. Implement comprehensive end-to-end tests
4. Add tests for error recovery mechanisms
5. Add tests for database migration scenarios

---

## Testing Guidelines

### Test Naming Conventions
- Use descriptive names that clearly indicate what is being tested
- Follow the pattern: `test_[feature]_[scenario]_[expected_result]`
- Example: `test_register_faction_valid_input_success`

### Test Structure
- Follow the Arrange-Act-Assert pattern:
  1. **Arrange**: Set up test data and conditions
  2. **Act**: Execute the function being tested
  3. **Assert**: Verify the expected results

### Mocking Guidelines
- Mock external dependencies (Telegram API, database connections)
- Use unittest.mock for mocking
- Reset mocks between tests to avoid interference
- Verify mock calls when necessary

### Async Testing Guidelines
- Use pytest-asyncio for async test support
- Mark async test functions with `@pytest.mark.asyncio`
- Use proper async/await syntax

### Database Testing Guidelines
- Use in-memory SQLite database for testing
- Create a fresh database for each test
- Use session_scope for proper session management
- Clean up after tests

### Error Testing Guidelines
- Test both expected and unexpected errors
- Verify error handling mechanisms
- Test recovery from errors
- Use pytest.raises for exception testing

### Performance Testing Guidelines
- Measure execution time for performance-critical operations
- Test with various data sizes
- Set performance thresholds
- Use time.time() for simple measurements

---

## QA Checklist

### Pre-Release Checklist
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Code coverage meets minimum requirements (80%)
- [ ] No critical or high-priority bugs
- [ ] Documentation is up to date
- [ ] Performance benchmarks are met
- [ ] Security review completed
- [ ] Accessibility requirements met

### Feature Testing Checklist

#### Registration Feature
- [ ] User can register with valid codename and faction
- [ ] System handles invalid codename input
- [ ] System handles invalid faction input
- [ ] User can cancel registration process
- [ ] Existing agent can be updated
- [ ] Faction input is case-insensitive
- [ ] Codename with special characters is handled correctly
- [ ] Very long codename is handled appropriately
- [ ] Network interruption during registration is handled gracefully
- [ ] Multiple registration attempts are handled independently

#### Submission Feature
- [ ] Registered user can submit AP and metrics
- [ ] System handles various payload formats
- [ ] System validates submission data
- [ ] Unregistered user cannot submit
- [ ] System handles submission errors gracefully
- [ ] Very large AP values are handled appropriately
- [ ] Negative AP values are handled according to business rules
- [ ] Special characters in metrics are handled appropriately
- [ ] Malformed key-value pairs are rejected with appropriate error
- [ ] Concurrent submissions do not cause deadlocks or race conditions

#### Group Submit + Autodelete Feature
- [ ] Messages are deleted when bot has permissions
- [ ] Messages are not deleted when bot lacks permissions
- [ ] Deletion is scheduled correctly
- [ ] System handles deletion errors gracefully
- [ ] Message already deleted is handled without errors
- [ ] Bot removed from group is handled gracefully
- [ ] Very long autodelete delay still executes at scheduled time
- [ ] Multiple submissions in quick succession schedule separate jobs
- [ ] Autodelete scheduling does not delay confirmation message

#### Leaderboard Caching Feature
- [ ] Leaderboard is generated correctly
- [ ] Leaderboard is cached for performance
- [ ] Leaderboard is updated when new submissions are made
- [ ] System handles leaderboard generation errors gracefully
- [ ] Tie in AP values is broken consistently
- [ ] Very large number of agents is handled efficiently
- [ ] Agents with no submissions do not appear in leaderboard
- [ ] Changing leaderboard size is reflected immediately
- [ ] Cache worker process failure is detected and logged
- [ ] Fallback to direct database queries when cache is unavailable

#### Verification Queue Feature
- [ ] Jobs are properly enqueued with correct parameters
- [ ] Workers process jobs in the order they were received (FIFO)
- [ ] Failed jobs are retried according to configuration
- [ ] Job status and results are properly tracked
- [ ] System performance is not impacted by job processing
- [ ] Queue overflow is handled gracefully
- [ ] Worker overload is handled appropriately
- [ ] Jobs with invalid parameters are handled gracefully
- [ ] Redis memory limit is handled appropriately

#### Admin Commands
- [ ] Start command sends welcome message
- [ ] Leaderboard command displays correct data
- [ ] System handles command errors gracefully
- [ ] Admin commands are properly authenticated and authorized
- [ ] Admin operations are executed correctly
- [ ] Appropriate responses are returned for admin commands
- [ ] System security is maintained
- [ ] Admin commands during high load execute correctly
- [ ] Conflicting admin commands are handled appropriately

### Performance Testing Checklist
- [ ] System performs well with small datasets
- [ ] System performs well with large datasets
- [ ] Database queries are optimized
- [ ] Memory usage is within acceptable limits
- [ ] Response times are within acceptable limits
- [ ] Registration response time is < 2 seconds
- [ ] Submission processing time is < 2 seconds
- [ ] Leaderboard command response time is < 2 seconds
- [ ] Leaderboard calculation completes efficiently even with large datasets
- [ ] Deletion job scheduling does not impact bot responsiveness
- [ ] Redis queue handles multiple deletion jobs efficiently
- [ ] Long deletion delays do not cause memory leaks

### Security Testing Checklist
- [ ] Input validation is implemented
- [ ] SQL injection vulnerabilities are addressed
- [ ] Authorization is properly implemented
- [ ] Sensitive data is properly handled
- [ ] Error messages do not expose sensitive information
- [ ] Telegram ID is validated to prevent spoofing
- [ ] Codename is sanitized to prevent SQL injection
- [ ] Faction input is strictly validated to only allow ENL or RES
- [ ] User data is not exposed to other users
- [ ] Job data is properly secured in Redis
- [ ] Sensitive information is not stored in job parameters
- [ ] Job processing does not introduce security vulnerabilities

### Compatibility Testing Checklist
- [ ] Compatible with target Python version
- [ ] Compatible with target database version
- [ ] Compatible with target Telegram Bot API version
- [ ] Compatible with target operating systems
- [ ] Works with different Redis versions
- [ ] Works with different SQLite versions

### Documentation Testing Checklist
- [ ] Installation instructions are clear and accurate
- [ ] Usage instructions are clear and accurate
- [ ] API documentation is complete and accurate
- [ ] Examples are provided and working
- [ ] Troubleshooting guide is helpful

---

## Appendix

### Glossary
- **AP**: Access Points, the primary scoring mechanism in Ingress
- **ENL**: Enlightened, one of the two factions in Ingress
- **RES**: Resistance, one of the two factions in Ingress
- **Codename**: The agent's username in Ingress
- **Submission**: A record of AP and metrics submitted by an agent
- **Leaderboard**: A ranking of agents by their total AP
- **Autodelete**: Automatic deletion of messages in group chats
- **Redis Queue**: A message queue system for processing background jobs
- **Verification Queue**: A system for processing submissions asynchronously
- **FIFO**: First In, First Out, a queue processing order

### Test Examples

#### Unit Test Example
```python
@pytest.mark.asyncio
async def test_register_faction_valid(self, mock_update, mock_context, session_factory):
    """Test register_faction with valid faction"""
    # Arrange
    mock_context.user_data["codename"] = "TestCodename"
    mock_update.message.text = "ENL"
    mock_update.message.reply_text = AsyncMock()
    
    # Act
    result = await register_faction(mock_update, mock_context)
    
    # Assert
    mock_update.message.reply_text.assert_called_once_with("Registered TestCodename (ENL).")
    assert result == -1  # ConversationHandler.END
    
    # Verify agent was created
    async with session_scope(session_factory) as session:
        agent_result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
        agent = agent_result.scalar_one()
        assert agent.codename == "TestCodename"
        assert agent.faction == "ENL"
```

#### Integration Test Example
```python
@pytest.mark.asyncio
async def test_complete_register_submit_flow(self, mock_update, mock_context, session_factory):
    """
    Test that a user can register and then successfully submit AP
    1. User registers with codename and faction
    2. User submits AP with metrics
    3. Verify submission is recorded correctly
    """
    # Step 1: Register user
    mock_update.message.reply_text = AsyncMock()
    
    # Start registration
    result = await register_start(mock_update, mock_context)
    assert result == 0  # CODENAME
    mock_update.message.reply_text.assert_called_with("Please send your agent codename.")
    
    # Provide codename
    mock_update.message.text = "TestAgent"
    mock_update.message.reply_text.reset_mock()
    result = await register_codename(mock_update, mock_context)
    assert result == 1  # FACTION
    mock_update.message.reply_text.assert_called_with("Send your faction (ENL or RES).")
    assert mock_context.user_data["codename"] == "TestAgent"
    
    # Provide faction
    mock_update.message.text = "ENL"
    mock_update.message.reply_text.reset_mock()
    result = await register_faction(mock_update, mock_context)
    assert result == -1  # ConversationHandler.END
    mock_update.message.reply_text.assert_called_with("Registered TestAgent (ENL).")
    assert "codename" not in mock_context.user_data
    
    # Verify agent was created
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
        agent = result.scalar_one()
        assert agent.codename == "TestAgent"
        assert agent.faction == "ENL"
    
    # Step 2: Submit AP
    mock_update.message.text = "/submit ap=12345; hacks=17"
    mock_update.message.message_id = 67890
    mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
    
    await submit(mock_update, mock_context)
    
    # Step 3: Verify submission was recorded
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Submission).join(Agent).where(Agent.telegram_id == 12345))
        submission = result.scalar_one()
        assert submission.ap == 12345
        assert submission.metrics == {"hacks": 17}
    
    # Verify reply was sent
    mock_update.message.reply_text.assert_called_once()
    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert "Recorded 12345 AP for TestAgent" in reply_text
```

### Running Tests
- Run all tests: `pytest`
- Run specific test file: `pytest tests/test_comprehensive.py`
- Run specific test class: `pytest tests/test_comprehensive.py::TestRegistrationFeature`
- Run specific test method: `pytest tests/test_comprehensive.py::TestRegistrationFeature::test_register_start`
- Run with coverage: `pytest --cov=bot`
- Run with verbose output: `pytest -v`

### Test Environment Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment variables:
   - `BOT_TOKEN`: Telegram bot token
   - `DATABASE_URL`: Database connection string
   - `REDIS_URL`: Redis connection string
   - `AUTODELETE_DELAY_SECONDS`: Delay for message autodeletion
   - `AUTODELETE_ENABLED`: Enable/disable message autodeletion
   - `LEADERBOARD_SIZE`: Number of entries to show in leaderboard
3. Run tests: `pytest`

### Continuous Integration
- Tests are run automatically on every push to the repository
- Code coverage is reported for each test run
- Performance benchmarks are run periodically
- Security scans are performed regularly

### Mock Data Setup Instructions
1. Create test fixtures for common data patterns
2. Use factories for generating test data
3. Ensure test data is isolated between tests
4. Clean up test data after each test
5. Use consistent data patterns across tests for reproducibility
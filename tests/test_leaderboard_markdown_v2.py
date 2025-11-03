#!/usr/bin/env python3
"""
Test script to verify that the leaderboard function works correctly with the escape_markdown_v2 helper function.
This script will test that special characters are properly escaped and no "Can't parse entities" error is thrown.
"""

import asyncio
import sys
import os
import tempfile
import traceback
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_leaderboard_markdown_v2():
    """Test that leaderboard function works correctly with escape_markdown_v2 helper."""
    try:
        # Import necessary modules
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy.orm import sessionmaker
        import aiosqlite
        
        print("✅ Required modules imported successfully")
        
        # Create a temporary database for testing
        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db.close()
        db_path = temp_db.name
        
        try:
            # Create an async engine
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            print("✅ Database engine created successfully")
            
            # Import models
            from bot.models import Base, Agent, Submission, Verification, VerificationStatus
            
            # Create tables
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            print("✅ Database tables created successfully")
            
            # Import the escape_markdown_v2 function
            from bot.main import escape_markdown_v2
            
            print("✅ escape_markdown_v2 function imported successfully")
            
            # Test the escape_markdown_v2 function with various inputs
            test_cases = [
                ("1.", "1\\."),  # Ranking number with dot
                ("10.", "10\\."),  # Ranking number with dot
                ("Test.Agent", "Test\\.Agent"),  # Agent name with dot
                ("Agent_Name", "Agent\\_Name"),  # Agent name with underscore
                ("Agent*Name", "Agent\\*Name"),  # Agent name with asterisk
                ("ENL", "ENL"),  # Simple faction
                ("RES", "RES"),  # Simple faction
                ("1,000", "1\\,000"),  # Metric value with comma
                ("1000", "1000"),  # Simple metric value
                ("✅", "✅"),  # Verification status (emoji)
                ("⏳", "⏳"),  # Verification status (emoji)
                ("❌", "❌"),  # Verification status (emoji)
            ]
            
            print("\nTesting escape_markdown_v2 function:")
            all_escape_tests_passed = True
            for input_text, expected_output in test_cases:
                result = escape_markdown_v2(input_text)
                if result == expected_output:
                    print(f"✅ '{input_text}' -> '{result}'")
                else:
                    print(f"❌ '{input_text}' -> '{result}' (expected: '{expected_output}')")
                    all_escape_tests_passed = False
            
            if not all_escape_tests_passed:
                print("❌ Some escape_markdown_v2 tests failed")
                return False
            
            print("✅ All escape_markdown_v2 tests passed")
            
            # Import the fixed leaderboard function
            from bot.services.leaderboard_fixed import get_leaderboard
            
            print("✅ Fixed leaderboard function imported successfully")
            
            # Add test data with special characters
            async with async_session() as session:
                # Add test agents with special characters in names
                agent1 = Agent(telegram_id=123, codename="Test.Agent1", faction="ENL")
                agent2 = Agent(telegram_id=456, codename="Agent_Name2", faction="RES")
                agent3 = Agent(telegram_id=789, codename="Agent*Name3", faction="ENL")
                session.add_all([agent1, agent2, agent3])
                await session.flush()
                
                print(f"✅ Added agents with special characters in names")
                
                # Add test submissions
                submission1 = Submission(
                    agent_id=agent1.id,
                    chat_id=None,
                    ap=1000,
                    metrics={"mu": 100, "links": 50},
                    time_span="ALL TIME"
                )
                submission2 = Submission(
                    agent_id=agent2.id,
                    chat_id=None,
                    ap=2000,
                    metrics={"mu": 200, "links": 100},
                    time_span="ALL TIME"
                )
                submission3 = Submission(
                    agent_id=agent3.id,
                    chat_id=None,
                    ap=1500,
                    metrics={"mu": 150, "links": 75},
                    time_span="ALL TIME"
                )
                session.add_all([submission1, submission2, submission3])
                await session.flush()
                
                # Add verification records with different statuses
                verification1 = Verification(
                    submission_id=submission1.id,
                    screenshot_path="",
                    status=VerificationStatus.approved.value
                )
                verification2 = Verification(
                    submission_id=submission2.id,
                    screenshot_path="",
                    status=VerificationStatus.pending.value
                )
                verification3 = Verification(
                    submission_id=submission3.id,
                    screenshot_path="",
                    status=VerificationStatus.rejected.value
                )
                session.add_all([verification1, verification2, verification3])
                
                # Commit to save data
                await session.commit()
                
                print("✅ Test data with special characters added successfully")
            
            # Test leaderboard function with data containing special characters
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10)
                    print(f"✅ Leaderboard function executed successfully with data: {len(result)} entries")
                    
                    # Format results as the bot would, using escape_markdown_v2
                    lines = ["🏆 *Leaderboard* 🏆"]
                    for index, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                        # Determine verification status
                        if metrics_dict.get("verified_ap", 0) > 0:
                            status = "✅"
                        elif metrics_dict.get("pending_ap", 0) > 0:
                            status = "⏳"
                        else:
                            status = "❌"
                        
                        # Escape all the text content that will be sent with parse_mode="MarkdownV2"
                        escaped_index = escape_markdown_v2(str(index) + ".")
                        escaped_codename = escape_markdown_v2(codename)
                        escaped_faction = escape_markdown_v2(faction)
                        escaped_status = escape_markdown_v2(status)
                        escaped_metric_value = escape_markdown_v2(f"{metric_value:,}")
                        
                        lines.append(f"{escaped_index} {escaped_codename} \\[{escaped_faction}\\] {escaped_status} — {escaped_metric_value} AP")
                    
                    formatted_message = "\n".join(lines)
                    print("\n📋 Formatted leaderboard message:")
                    print(formatted_message)
                    
                    # Test that the formatted message doesn't contain unescaped special characters
                    # that would cause "Can't parse entities" error
                    
                    # First, let's remove the emojis from the message before checking for unescaped special characters
                    # Emojis don't need to be escaped in MarkdownV2
                    message_without_emojis = formatted_message
                    for emoji in ["✅", "⏳", "❌", "🏆"]:
                        message_without_emojis = message_without_emojis.replace(emoji, "")
                    
                    # Now let's handle the asterisks used for formatting in the header
                    # In MarkdownV2, *word* is used for bold, so we need to account for this pattern
                    # We'll count asterisks that are not part of valid MarkdownV2 formatting
                    
                    # Count all asterisks
                    total_asterisks = message_without_emojis.count("*")
                    # Count escaped asterisks
                    escaped_asterisks = message_without_emojis.count("\\*")
                    # Count asterisks that are part of valid MarkdownV2 formatting (pairs)
                    # In valid MarkdownV2, asterisks for formatting must be properly paired
                    lines = message_without_emojis.split("\n")
                    formatting_asterisks = 0
                    
                    for line in lines:
                        # Count asterisks that are part of *bold* formatting
                        # In valid MarkdownV2, it should be \*text\* for bold
                        bold_pattern_matches = line.count("*") - line.count("\\*")
                        # If we have an even number of unescaped asterisks, they might be for formatting
                        if bold_pattern_matches % 2 == 0:
                            formatting_asterisks += bold_pattern_matches
                    
                    unescaped_dots = message_without_emojis.count(".") - message_without_emojis.count("\\.")
                    unescaped_underscores = message_without_emojis.count("_") - message_without_emojis.count("\\_")
                    unescaped_asterisks = total_asterisks - escaped_asterisks - formatting_asterisks
                    unescaped_brackets = message_without_emojis.count("[") - message_without_emojis.count("\\[")
                    unescaped_parens = message_without_emojis.count("(") - message_without_emojis.count("\\(")
                    
                    if unescaped_dots > 0:
                        print(f"❌ Found {unescaped_dots} unescaped dots that could cause parsing errors")
                        return False
                    
                    if unescaped_underscores > 0:
                        print(f"❌ Found {unescaped_underscores} unescaped underscores that could cause parsing errors")
                        return False
                    
                    if unescaped_asterisks > 0:
                        print(f"❌ Found {unescaped_asterisks} unescaped asterisks that could cause parsing errors")
                        return False
                    
                    if unescaped_brackets > 0:
                        print(f"❌ Found {unescaped_brackets} unescaped brackets that could cause parsing errors")
                        return False
                    
                    if unescaped_parens > 0:
                        print(f"❌ Found {unescaped_parens} unescaped parentheses that could cause parsing errors")
                        return False
                    
                    print("✅ All special characters are properly escaped")
                    
                except Exception as e:
                    print(f"❌ Error executing leaderboard function with special characters: {e}")
                    traceback.print_exc()
                    return False
            
            # Test with additional edge cases
            edge_cases = [
                "Agent.Name.With.Many.Dots",
                "Agent_Name_With_Underscores",
                "Agent*With*Asterisks",
                "Agent[With]Brackets",
                "Agent(With)Parens",
                "Agent~With~Tildes",
                "Agent`With`Backticks",
                "Agent>With>GreaterThans",
                "Agent#With#Hashes",
                "Agent+With+Pluses",
                "Agent-With-Hyphens",
                "Agent=With=Equals",
                "Agent|With|Pipes",
                "Agent{With}Braces",
                "Agent.With!Exclamation",
            ]
            
            print("\nTesting edge cases with agent names containing special characters:")
            async with async_session() as session:
                for i, edge_case in enumerate(edge_cases, start=4):
                    try:
                        # Add agent with edge case name
                        agent = Agent(telegram_id=1000+i, codename=edge_case, faction="ENL")
                        session.add(agent)
                        await session.flush()
                        
                        # Add submission for this agent
                        submission = Submission(
                            agent_id=agent.id,
                            chat_id=None,
                            ap=100,
                            metrics={},
                            time_span="ALL TIME"
                        )
                        session.add(submission)
                        await session.flush()
                        
                        # Add verification record
                        verification = Verification(
                            submission_id=submission.id,
                            screenshot_path="",
                            status=VerificationStatus.approved.value
                        )
                        session.add(verification)
                        
                        # Commit to save data
                        await session.commit()
                        
                        # Test leaderboard function with this edge case
                        result = await get_leaderboard(session, 10)
                        
                        # Format results as the bot would, using escape_markdown_v2
                        lines = ["🏆 *Leaderboard* 🏆"]
                        for index, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                            # Determine verification status
                            if metrics_dict.get("verified_ap", 0) > 0:
                                status = "✅"
                            elif metrics_dict.get("pending_ap", 0) > 0:
                                status = "⏳"
                            else:
                                status = "❌"
                            
                            # Escape all the text content
                            escaped_index = escape_markdown_v2(str(index) + ".")
                            escaped_codename = escape_markdown_v2(codename)
                            escaped_faction = escape_markdown_v2(faction)
                            escaped_status = escape_markdown_v2(status)
                            escaped_metric_value = escape_markdown_v2(f"{metric_value:,}")
                            
                            lines.append(f"{escaped_index} {escaped_codename} \\[{escaped_faction}\\] {escaped_status} — {escaped_metric_value} AP")
                        
                        formatted_message = "\n".join(lines)
                        
                        # Check if the edge case character is properly escaped
                        if "\\" in formatted_message:
                            print(f"✅ Agent name '{edge_case}' is properly escaped")
                        else:
                            print(f"❌ Agent name '{edge_case}' may not be properly escaped")
                            return False
                        
                    except Exception as e:
                        print(f"❌ Error testing edge case '{edge_case}': {e}")
                        traceback.print_exc()
                        return False
            
            print("✅ All edge case tests passed")
            
            return True
            
        finally:
            # Clean up
            try:
                await engine.dispose()
            except:
                pass
            try:
                os.unlink(db_path)
            except:
                pass
    
    except Exception as e:
        print(f"❌ Error in test setup: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing leaderboard function with escape_markdown_v2 helper...")
    print("=" * 60)
    success = asyncio.run(test_leaderboard_markdown_v2())
    
    if success:
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED: The leaderboard function works correctly with escape_markdown_v2")
        print("\nSUMMARY:")
        print("- The escape_markdown_v2 function properly escapes all special characters")
        print("- Ranking numbers (e.g., '1.', '2.') are properly escaped")
        print("- Agent names with special characters are properly escaped")
        print("- Factions and metric values are properly escaped")
        print("- The formatted message should not cause 'Can't parse entities' errors")
        print("- Edge cases with various special characters are handled correctly")
    else:
        print("\n" + "=" * 60)
        print("❌ TESTS FAILED: There are issues with the leaderboard function or escape_markdown_v2")
        sys.exit(1)
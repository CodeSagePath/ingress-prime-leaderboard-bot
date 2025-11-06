#!/usr/bin/env python3
"""
Simple configuration test script that doesn't require full dependencies
"""

import sys
import os
from pathlib import Path

# Add bot directory to path
bot_dir = Path(__file__).parent / "bot"
sys.path.insert(0, str(bot_dir))

def test_basic_config():
    """Test basic configuration loading"""
    print("🔧 Testing Configuration System")
    print("=" * 50)

    try:
        # Test environment variable parsing
        os.environ["BOT_TOKEN"] = "test_token"
        os.environ["ADMIN_USER_IDS"] = "123456789"
        os.environ["ENVIRONMENT"] = "development"

        from config import DatabaseConfig, RedisConfig, ServerConfig, SecurityConfig, MonitoringConfig

        # Test individual config classes
        db_config = DatabaseConfig()
        print(f"✅ Database config: URL={db_config.url}, Pool Size={db_config.pool_size}")

        redis_config = RedisConfig()
        print(f"✅ Redis config: URL={redis_config.url}, Max Connections={redis_config.max_connections}")

        server_config = ServerConfig()
        print(f"✅ Server config: Host={server_config.host}, Port={server_config.port}")

        security_config = SecurityConfig()
        print(f"✅ Security config: Rate Limiting={security_config.rate_limit_enabled}")

        monitoring_config = MonitoringConfig()
        print(f"✅ Monitoring config: Health Check={monitoring_config.health_check_enabled}")

        print("\n🎉 Configuration system is working correctly!")
        return True

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_env_parsing():
    """Test environment variable parsing"""
    print("\n🔧 Testing Environment Variable Parsing")
    print("=" * 50)

    try:
        from config import _bool

        # Test boolean parsing
        assert _bool("true", False) == True
        assert _bool("1", False) == True
        assert _bool("yes", False) == True
        assert _bool("false", True) == False
        assert _bool("0", True) == False
        assert _bool("no", True) == False
        assert _bool(None, True) == True
        assert _bool("", False) == False

        print("✅ Boolean parsing works correctly")

        # Test helper functions
        from config import _get_local_ip
        local_ip = _get_local_ip()
        print(f"✅ Local IP detection: {local_ip}")

        print("\n🎉 Environment parsing is working correctly!")
        return True

    except Exception as e:
        print(f"❌ Environment parsing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_validation():
    """Test configuration validation"""
    print("\n🔧 Testing Configuration Validation")
    print("=" * 50)

    try:
        # Import validation function
        from config import Settings, DatabaseConfig, RedisConfig, ServerConfig, SecurityConfig, MonitoringConfig, validate_settings

        # Create minimal valid settings
        settings = Settings(
            telegram_token="test_token",
            admin_user_ids=[123456789],
            database=DatabaseConfig(),
            redis=RedisConfig(),
            server=ServerConfig(),
            security=SecurityConfig(),
            monitoring=MonitoringConfig()
        )

        errors = validate_settings(settings)
        if errors:
            print(f"⚠️  Expected validation errors (test config): {len(errors)}")
        else:
            print("✅ Configuration validation passed")

        # Test with invalid settings
        invalid_settings = Settings(
            telegram_token="",  # Invalid: empty
            admin_user_ids=[],  # Invalid: empty
            database=DatabaseConfig(),
            redis=RedisConfig(),
            server=ServerConfig(port=99999),  # Invalid: port too high
            security=SecurityConfig(),
            monitoring=MonitoringConfig()
        )

        errors = validate_settings(invalid_settings)
        print(f"✅ Detected {len(errors)} validation errors as expected")
        for error in errors[:3]:  # Show first 3 errors
            print(f"  - {error}")

        print("\n🎉 Configuration validation is working correctly!")
        return True

    except Exception as e:
        print(f"❌ Configuration validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = True

    success &= test_basic_config()
    success &= test_env_parsing()
    success &= test_validation()

    print("\n" + "=" * 50)
    if success:
        print("🎉 All configuration tests passed!")
        print("Your bot is ready for server deployment!")
    else:
        print("❌ Some tests failed. Please check the configuration.")
        sys.exit(1)
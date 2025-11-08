module.exports = {
  apps: [
    {
      name: "ingress-bot",
      script: "main.py",
      cwd: "/home/botadmin/bots/ingress-prime-leaderboard-bot",
      interpreter: "/home/botadmin/bots/ingress-prime-leaderboard-bot/venv/bin/python",
      env: {
        PYTHONUNBUFFERED: "1",
        BOT_MESSAGE_CLEANUP_MINUTES: "5"
        // TELEGRAM_TOKEN: "xxx"   // prefer loading from environment or .env file
      },
      instances: 1, // force 1 instance to prevent conflicts
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      error_file: "./logs/ingress-bot-error.log",
      out_file: "./logs/ingress-bot-out.log",
      log_file: "./logs/ingress-bot-combined.log",
      time: true,
      // Add environment variables for bot message auto-deletion
      env_production: {
        PYTHONUNBUFFERED: "1",
        BOT_MESSAGE_CLEANUP_MINUTES: "5"
      }
    },
    {
      name: "sage-bot",
      script: "main.py",
      cwd: "/home/botadmin/bots/sage-bot",
      interpreter: "/home/botadmin/bots/sage-bot/venv/bin/python",
      env: { PYTHONUNBUFFERED: "1" }
    },
    {
      name: "whotalks-bot",
      script: "main.py",
      cwd: "/home/botadmin/bots/whotalks-bot",
      interpreter: "/home/botadmin/bots/whotalks-bot/venv/bin/python",
      env: { PYTHONUNBUFFERED: "1" }
    }
  ]
}
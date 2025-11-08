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
      instances: 1, // force 1 instance for unified operation
      autorestart: true,
      watch: false,
      kill_timeout: 5000, // Allow graceful shutdown
      restart_delay: 5000
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
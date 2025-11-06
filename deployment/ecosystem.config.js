module.exports = {
  apps: [{
    name: 'ingress-bot',
    script: 'main.py',
    interpreter: '/var/www/ingress-prime-leaderboard-bot/venv/bin/python',
    cwd: '/var/www/ingress-prime-leaderboard-bot',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    },
    error_file: '/var/log/ingress-bot/error.log',
    out_file: '/var/log/ingress-bot/out.log',
    log_file: '/var/log/ingress-bot/combined.log',
    time: true
  }]
};
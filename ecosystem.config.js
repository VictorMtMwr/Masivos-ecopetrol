module.exports = {
  apps: [{
    name: 'masivos-ecopetrol',
    script: './venv/bin/gunicorn',
    args: '--bind 0.0.0.0:5000 --workers 2 --timeout 1800 --access-logfile - --error-logfile - service:app',
    cwd: '/home/victor/dev/Masivos-ecopetrol',
    interpreter: 'none',
    autorestart: true,
    max_restarts: 10,
    watch: false,
    env: {
      PYTHONUNBUFFERED: '1'
    }
  }]
};

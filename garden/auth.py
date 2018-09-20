import functools
import string
import random
import uuid
import time
from garden.model import Client

from flask import (
    Blueprint, g, request, jsonify, session
)

from werkzeug.security import check_password_hash, generate_password_hash

from garden.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        nickname = request.form['nickname']
        db = get_db()
        error = None

        if not nickname:
            error = 'Nickname is required.'

        if error is None:

            identifier = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(255))
            secret = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(255))

            client = Client({'identifier': identifier, 'secret': generate_password_hash(secret), 'active': 0, 'nickname': nickname})
            client.save()
            client.refresh()
            client.save()

            output = client.dictionary() 

            return jsonify(output), 200 

        return jsonify(error=error), 400 

@bp.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        secret = request.form['secret']
        db = get_db()
        error = None
        client = db.execute(
            'SELECT * FROM client WHERE identifier = ?', (identifier,)
        ).fetchone()

        if client is None:
            error = 'Invalid client.'
        elif not check_password_hash(client['secret'], secret):
            error = 'Authentication failed.'
        elif not client['active']:
            error = 'Your account is not active.'

        if error is None:
            session.clear()
            session['client_uuid'] = client['uuid']
            session['login_time'] = time.time()
            session['last_request_time'] = time.time()
            return jsonify({'authenticated': True}), 200

        return jsonify({'authenticated': False, 'error': error}), 400

@bp.before_app_request
def load_authenticated_client():
    client_uuid = session.get('client_uuid')

    if client_uuid is None:
        g.client = None
    else:
        if time.time() - session.get('last_request_time') > 24*3600:
            g.client = None
            session.clear()
            return
        elif time.time() - session.get('login_time') > 14*24*3600:
            g.client = None
            session.clear()
            return

        g.client = get_db().execute(
            'SELECT * FROM client WHERE uuid = ?', (client_uuid,)
        ).fetchone()

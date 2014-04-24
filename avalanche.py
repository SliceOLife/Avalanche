# all the imports
from uuid import uuid4
from base64 import b64encode
import hashlib
from datetime import datetime
import sys

from os import urandom
import os
from flask import Flask, request, redirect, url_for, \
    abort, render_template, flash, make_response, jsonify, send_from_directory, \
    g
from flask.ext.httpauth import HTTPBasicAuth
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager, login_user, logout_user, current_user, login_required
from passlib.apps import custom_app_context as pwd_context





# init config
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['UPLOAD_FOLDER'] = 'uploads/source/'

# extra config
ALLOWED_EXTENSIONS = {'zip'}
ROLE_USER = 0
ROLE_ADMIN = 1


# Extensions and such
auth = HTTPBasicAuth()
db = SQLAlchemy(app)
lm = LoginManager()
lm.init_app(app)
app.config.from_object(__name__)


class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(32))
    body = db.Column(db.Text())
    lang = db.Column(db.String(32))
    timestamp = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    fileloc = db.Column(db.String(100))
    isactive = db.Column(db.Integer)

    def __repr__(self):
        return '<Entry %r>' % (self.body)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True)
    nickname = db.Column(db.String(32))
    role = db.Column(db.SmallInteger, default=ROLE_USER)
    issues = db.relationship('Entry', backref='creator', lazy='dynamic')
    active_issues = db.Column(db.Integer, default=0)
    api_id = db.Column(db.String(32))

    def hash_password(self, password):
        self.password_hash = pwd_context.encrypt(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    def generate_api_id(self):
        self.api_id = b64encode(urandom(9))

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return unicode(self.id)

    def __repr__(self):
        return '<User %r>' % (self.username)

    def avatar(self):
        return 'http://www.gravatar.com/avatar/' + hashlib.md5(self.email).hexdigest() + '?d=mm&s=100'


# utils and such

def getUserAvatar(email):
  return 'http://www.gravatar.com/avatar/' + hashlib.md5(email).hexdigest() + '?d=mm&s=100'


@app.before_request
def before_request():
    g.user = current_user
    # Dirty hack for new nav
    if not g.user.is_authenticated():
        g.user.api_id = "N/A"
        g.user.issues = "N/A"
        g.user.avatar = getUserAvatar("anonymous@drone.codecove.net")
        g.user.nickname = "Anonymous"
        g.user.username = "Anonymous"
        g.user.email = "anonymous@drone.codecove.net"
    else:
        g.user.avatar = getUserAvatar(g.user.email)
    g.app_name = "Avalanche Alpha"


@lm.user_loader
def load_user(uid):
    return User.query.get(int(uid))


def is_empty(any_structure):
    if any_structure:
        return False
    else:
        return True


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def handleUpload(upload):
  if upload and allowed_file(upload.filename):
      upload = 'source_' + str(uuid4()) + '.' + upload.filename.rsplit('.', 1)[1]
      fPath = os.path.join(app.config['UPLOAD_FOLDER'], upload)
      file.save(fPath)
      fileLoc = '/uploads/source/' + upload
  else:
      fileLoc = ""
  return fileLoc


# error handling

@app.errorhandler(404)
def page_not_found(e):
    print(e)
    return render_template('error/404.html'), 404


@app.route('/')
def show_main():
    if not g.user.is_authenticated():
        return redirect(url_for('show_login'))
    else:
        return redirect(url_for('show_profile'))


@app.route('/add', methods=['POST'])
def add_entry():
    if not g.user.is_authenticated():
        abort(401)

    if request.form['title'] is None or request.form['body'] is None or request.form['lang'] is None:
        flash('Onvoldoende gegevens ingevuld, probeer het opnieuw.')
        return redirect(url_for('post_entry'))
    else:
        fileupload = handleUpload(request.files['file'])
        entry = Entry(title=request.form['title'], body=request.form['body'], lang=request.form['lang'],
                      timestamp=datetime.utcnow(), creator=g.user, fileloc=fileupload, isactive=1)
        db.session.add(entry)

        # Update user problem count
        g.user.active_issues += 1
        db.session.add(g.user)
        db.session.commit()
        flash('Bedankt voor het posten van uw probleem!')
        return redirect(url_for('show_profile'))


@app.route('/createuser', methods=['POST'])
def add_user():
    if g.user.is_authenticated():
        flash('U bent al geregistreerd!')
        return redirect(url_for('show_main'))
    else:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        nickname = request.form['nickname']
        if username is None or password is None:
            abort(400)  # missing arguments
        if User.query.filter_by(username=username).first() is not None:
            abort(400)  # existing user
        user = User(username=username, email=email, nickname=nickname, role=ROLE_USER)
        user.hash_password(password)
        user.generate_api_id()
        db.session.add(user)
        db.session.commit()
        login_user(user)  # automatically login user after registration
        return redirect(url_for('show_profile'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    error = None

    if request.method == 'POST':
        user = User.query.filter_by(username=username).first()
        if not user or not user.verify_password(password):
            error = 'Foutieve gebruikersnaam en of wachtwoord!'
            return render_template('index.html', error=error)
        login_user(user)
        flash('U bent succesvol ingelogd')
        return redirect(url_for('show_main'))


@app.route('/register')
def register_new():
    return render_template('reg_new.html')


@app.route('/experimental/entries')
@login_required
def show_entries_exp():
    entries = Entry.query.all()
    return render_template('show_entries_exp.html', entries=entries)


@app.route('/post')
@login_required
def post_entry():
    return render_template('post_new.html')


@app.route('/projector')
@login_required
def show_entries_projector():
    #entries = Entry.query.all()
    #return render_template('show_entries_projector.html', entries=entries)
    abort(404)


@app.route('/test')
def test_buildpack_heroku():
    u = User.query.get(1)
    print u
    print u.issues.all()
    return redirect(url_for('show_login'))


@app.route('/profile')
def show_profile():
    if not g.user.is_authenticated():
        return redirect(url_for('show_login'))
    return render_template('profile.html', user=g.user)


@app.route('/index')
def show_login():
    return render_template('index.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('show_login'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# Admin routing

def is_authed_and_admin():
    if g.user.is_authenticated() and g.user.role == ROLE_ADMIN:
        return True


@app.route('/admin/index')
def admin_index():
    if is_authed_and_admin():
        return render_template('admin/index.html')
    else:
        return redirect(url_for('show_profile'))


@app.route('/admin/adduser')
def admin_adduser():
    if is_authed_and_admin():
        return render_template('admin/adduser.html')
    else:
        return redirect(url_for('show_profile'))


@app.route('/admin/users')
def admin_showusers():
    if is_authed_and_admin():
        Users = User.query.all()
        return render_template('admin/users.html', users=Users)
    else:
        return redirect(url_for('show_profile'))


@app.route('/admin/users/<int:userid>')
def admin_userdetail(userid):
    if is_authed_and_admin():
        currentUser = User.query.filter(id=userid).first()
        return render_template('admin/userdetail.html', user=currentUser)
    else:
        return redirect(url_for('show_profile'))


@app.route('/admin/killapp')
def admin_killapp():
    if is_authed_and_admin():
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        return 'Server shutting down...'
    else:
        return redirect(url_for('show_profile'))


@app.route('/admin/user/<string:func>/<int:userid>')
def admin_usertools(func, userid):
    if is_authed_and_admin():
        if func == "delete":
            isUser = User.query.filter_by(id=userid).first()
            if isUser:
                db.session.delete(isUser)
                db.session.commit()
    return redirect(url_for('admin_showusers'))


# API routing ( CRUD )

@app.route('/api/v1.0/users/', methods=['POST'])
def new_user():
    username = request.json.get('username')
    password = request.json.get('password')
    email = request.json.get('email')
    nickname = request.json.get('nickname')
    if username is None or password is None:
        abort(400)  # missing arguments
    if User.query.filter_by(username=username).first() is not None:
        abort(400)  # existing user
    user = User(username=username, email=email, nickname=nickname)
    user.hash_password(password)
    user.generate_api_id()
    db.session.add(user)
    db.session.commit()
    return jsonify({'username': user.username, 'api_id': user.api_id})


# Public API method. Gets list of all current issues in tracker.
@app.route('/api/v1.0/issues/<string:retype>', methods=['GET'])
def show_main_api(retype):
    if retype == "all":
        data = Entry.query.all()
    elif retype == "active":
        data = Entry.query.filter(Entry.isactive == 1).all()
    elif retype == "inactive":
        data = Entry.query.filter(Entry.isactive == 0).all()
    else:
        data = Entry.query.all()

    cols = ['id', 'title', 'body', 'lang', 'user_id', 'timestamp', 'fileloc', 'isactive']
    issue = [{col: getattr(d, col) for col in cols} for d in data]

    if is_empty(issue):
        response = jsonify({'error': 'no issues'})
        response.status_code = 404
        return response
    else:
        return jsonify(issues=issue)


# Public API method. Get specific issue by ID
@app.route('/api/v1.0/issues/<int:api_id>', methods=['GET'])
def show_entry_api(api_id):
    cols = ['title', 'body', 'lang', 'user_id', 'timestamp', 'fileloc', 'isactive']
    data = Entry.query.filter(Entry.id == api_id).all()
    issue = [{col: getattr(d, col) for col in cols} for d in data]

    if is_empty(issue):
        response = jsonify({'error': 'issue not found'})
        response.status_code = 404
        return response
    else:
        return jsonify(issue=issue)


# Private API method. Post a new issue to tracker.
# TODO: Look into file upload using post.
@app.route('/api/v1.0/issues/', methods=['POST'])
def post_entry_api():
    title = request.json.get('title')
    text = request.json.get('body')
    lang = request.json.get('lang')
    user_apid = request.json.get('api_id')
    fileupload = handleUpload(request.files['file'])

    if title is None or text is None or user_apid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    creator = User.query.filter_by(api_id=user_apid).first()
    if creator is not None:
        entry = Entry(title=title, body=text, lang=lang,
                      timestamp=datetime.utcnow(), creator=creator, fileloc=fileupload, isactive=1)
        # update creator problem count
        creator.active_issues += 1
        db.session.add(entry)
        db.session.commit()

        response = jsonify({'success': 'true', 'issue_id': entry.id})
        response.status_code = 201
        return response
    else:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)


# Private API method. Modify issue.
@app.route('/api/v1.0/issues/<int:issue_id>/update', methods=['POST'])
def update_entry_api(issue_id):
    title = request.json.get('title')
    text = request.json.get('body')
    lang = request.json.get('lang')
    user_apid = request.json.get('api_id')

    if title is None or text is None or user_apid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    creator = User.query.filter_by(api_id=user_apid).first()
    issue = Entry.query.filter_by(id=issue_id).first()

    if creator is not None:
        if issue.user_id is creator.id:
            if is_empty(issue):
                response = jsonify({'error': 'unknown issue'})
                response.status_code = 404
                return response
            else:
                issue.title = title
                issue.body = text
                issue.lang = lang
                issue.timestamp = datetime.utcnow()
                db.session.commit()

                response = jsonify({'success': 'true', 'uuid': uuniqueid})
                response.status_code = 200
                return response
        else:
            return make_response(jsonify({'error': "This issue doesn't belong to: " + creator.username}), 400)
    else:
        return make_response(jsonify({'error': 'Invalid user API key'}), 400)


# Private API method. Mark issue inactive.
@app.route('/api/v1.0/issues/<int:issue_id>/deactivate', methods=['POST'])
def inactive_entry_api(issue_id):
    user_apid = request.json.get('api_id')
    if user_apid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter_by(id=issue_id).first()

    if is_empty(issue):
        response = jsonify({'error': 'unknown issue'})
        response.status_code = 404
        return response

    creator = User.query.filter_by(api_id=user_apid).first()

    if creator is not None:
        if issue.user_id is creator.id:
            issue.isactive = 0
            creator.active_issues -= 1
            db.session.commit()

            response = jsonify({'success': 'true', 'issue_id': issue.id})
            response.status_code = 200
            return response
        else:
            return make_response(jsonify({'error': "This issue doesn't belong to: " + creator.username}), 400)
    else:
        return make_response(jsonify({'error': 'Invalid user API key'}), 400)


# Private API method. Mark issue active.
@app.route('/api/v1.0/issues/<int:issue_id>/activate', methods=['POST'])
def activate_entry_api(issue_id):
    user_apid = request.json.get('api_id')
    if user_apid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter_by(id=issue_id).first()

    if is_empty(issue):
        response = jsonify({'error': 'issue not found'})
        response.status_code = 404
        return response

    creator = User.query.filter_by(api_id=user_apid).first()

    if creator is not None:
        if issue.user_id is creator.id:
            issue.isactive = 1
            creator.active_issues += 1
            db.session.commit()

            response = jsonify({'success': 'true', 'issue_id': issue.id})
            response.status_code = 200
            return response
        else:
            return make_response(jsonify({'error': "This issue doesn't belong to: " + creator.username}), 400)
    else:
        return make_response(jsonify({'error': 'Invalid user API key'}), 400)


# Private API method. Delete issue.
@app.route('/api/v1.0/issues/<int:issue_id>/delete', methods=['POST'])
def delete_entry_api(issue_id):
    user_apid = request.json.get('api_id')
    if user_apid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter_by(id=issue_id).first()
    creator = User.query.filter_by(api_id=user_apid).first()

    if creator is not None:
        if issue.user_id is creator.id:
            db.session.delete(issue)
            creator.active_issues -= 1
            db.session.commit()
            # We need to kill the corresponding source files too if they exist
            sourcefile = os.path.dirname(os.path.realpath(sys.argv[0])) + issue.fileloc
            if os.path.isfile(sourcefile):
                os.remove(sourcefile)
            response = jsonify({'success': 'true', 'issue_id': issue.id})
            response.status_code = 200
            return response
        else:
          return make_response(jsonify({'error': "This issue doesn't belong to: " + creator.username}), 400)

    else:
      return make_response(jsonify({'error': 'Invalid user API key'}), 400)

if __name__ == '__main__':
    if not os.path.exists('app.db'):
        db.create_all()
    app.run(host='0.0.0.0', debug=True)

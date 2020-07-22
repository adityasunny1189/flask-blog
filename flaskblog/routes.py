import os
import secrets
from PIL import Image
from flask import render_template, redirect, request, url_for, flash, abort
from flaskblog.models import User, Post
from flaskblog.forms import SignUp, SignIn, UpdateProfile, PostForm, RequestResetForm, ResetPasswordForm
from flaskblog import app, db, bcrypt, mail
from flask_login import login_user, current_user, logout_user, login_required
from flask_socketio import SocketIO
from flask_mail import Message

socketio = SocketIO(app)

@app.route('/')
def index():
	page = request.args.get('page', 1, type = int)
	posts = Post.query.order_by(Post.date_posted.desc()).paginate(page = page, per_page = 5)
	return render_template('index.html', blog_posts = posts)


@app.route('/about')
def about():
	return render_template('about.html', title = 'about')

@app.route('/home')
def home():
	return redirect('/')

@app.route('/signup', methods = ['GET', 'POST'])
def signup():
	if current_user.is_authenticated:
		return redirect(url_for('home'))
	form = SignUp()
	if form.validate_on_submit():
		hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
		user = User(username = form.username.data, email = form.email.data, password = hashed_password)
		db.session.add(user)
		db.session.commit()
		flash('Your account has been created, now you can Signin', 'success')
		return redirect(url_for('signin'))
	return render_template('signup.html', title = 'Sign Up', form = form)

@app.route('/signin', methods = ['GET', 'POST'])
def signin():
	if current_user.is_authenticated:
		return redirect(url_for('home'))
	form = SignIn()
	if form.validate_on_submit():
		user = User.query.filter_by(email = form.email.data).first()
		if user and bcrypt.check_password_hash(user.password, form.password.data):
			login_user(user, remember = form.remember_me.data)
			next_page = request.args.get('next')
			return redirect(next_page) if next_page else redirect(url_for('home'))
		else:
			flash('Invalid Credentials', 'danger')
	return render_template('signin.html', title = 'Sign In', form = form)

@app.route('/logout')
def logout():
	logout_user()
	return redirect(url_for('home'))

def save_picture(form_picture):
	random_hex = secrets.token_hex(8)
	_, f_ext = os.path.splitext(form_picture.filename)
	picture_fn = random_hex + f_ext
	picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)
	output_size = (125, 125)
	i = Image.open(form_picture)
	i.thumbnail(output_size)
	i.save(picture_path)
	return picture_fn


@app.route('/account', methods = ['GET', 'POST'])
@login_required
def account():
	form = UpdateProfile()
	if form.validate_on_submit():
		if form.picture.data:
			picture_file = save_picture(form.picture.data)
			current_user.avatar = picture_file
		current_user.username = form.username.data
		current_user.email = form.email.data
		db.session.commit()
		flash('Your account has been updated', 'success')
		return redirect(url_for('account'))
	elif request.method == 'GET':
		form.username.data = current_user.username
		form.email.data = current_user.email
	image_file = url_for('static', filename = 'profile_pics/' + current_user.avatar)
	return render_template('account.html', title = 'profile', image_file = image_file, form = form)

@app.route('/post/new', methods = ['GET', 'POST'])
@login_required
def new_post():
	form = PostForm()
	if form.validate_on_submit():
		post = Post(title = form.title.data, content = form.content.data, author = current_user)
		db.session.add(post)
		db.session.commit()
		flash('Your Post has been created', 'success')
		return redirect(url_for('home'))
	return render_template('create_post.html', title = 'create post', form = form, legend = 'create post')

@app.route('/post/<int:post_id>')
def post(post_id):
	post = Post.query.get_or_404(post_id)
	return render_template('post.html', title = post.title, post = post)

@app.route('/post/<int:post_id>/update', methods = ['GET', 'POST'])
@login_required
def update_post(post_id):
	post = Post.query.get_or_404(post_id)
	if post.author != current_user:
		abort(403)
	form = PostForm()
	if form.validate_on_submit():
		post.title = form.title.data
		post.content = form.content.data
		db.session.commit()
		flash('Your Post has been updated', 'success')
		return redirect(url_for('post', post_id = post.id))
	elif request.method == 'GET':
		form.title.data = post.title
		form.content.data = post.content
	return render_template('create_post.html', title = 'Update post', form = form, legend = 'Update Post')

@app.route('/post/<int:post_id>/delete', methods = ['POST'])
@login_required
def delete_post(post_id):
	post = Post.query.get_or_404(post_id)
	if post.author != current_user:
		abort(403)
	db.session.delete(post)
	db.session.commit()
	flash('Your Post has been deleted', 'success')
	return redirect(url_for('home'))

@app.route('/user/<string:username>')
def user_post(username):
	user = User.query.filter_by(username = username).first_or_404()
	page = request.args.get('page', 1, type = int)
	posts = Post.query.filter_by(author = user).order_by(Post.date_posted.desc()).paginate(page = page, per_page = 5)
	return render_template('user_post.html', blog_posts = posts, user = user)


@app.route('/chat', methods = ['GET', 'POST'])
@login_required
def chat():
    return render_template('chat.html', title = "ChatBox")

def messageReceived(methods=['GET', 'POST']):
    print('message was received!!!')

@socketio.on('my event')
def handle_my_custom_event(json, methods=['GET', 'POST']):
    print('received my event: ' + str(json))
    socketio.emit('my response', json, callback=messageReceived)

def send_reset_email(user):
	token= user.get_reset_token()
	msg = Message('Password Reset Request', sender = "senderEmail@gmail.com", recipients = [user.email])
	msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token = token, _external = True)}

If you did not make this request then simply ignore this email and no changes will be made
'''
	mail.send(msg)


@app.route('/reset_password', methods = ['GET', 'POST'])
def reset_request():
	if current_user.is_authenticated:
		return redirect(url_for('home'))
	form = RequestResetForm()
	if form.validate_on_submit():
		user = User.query.filter_by(email = form.email.data).first()
		send_reset_email(user)
		flash('An email has been sent with instruction to reset your password.', 'info')
		return redirect(url_for('signin'))
	return render_template('reset_request.html', title = "Reset Password", form = form)

@app.route('/reset_password/<token>', methods = ['GET', 'POST'])
def reset_token(token):
	if current_user.is_authenticated:
		return redirect(url_for('home'))
	user = User.verify_reset_token(token)
	if user is None:
		flash('That is an invalid or expired token', 'warning')
		return redirect(url_for('reset_request'))
	form = ResetPasswordForm()
	if form.validate_on_submit():
		hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
		user.password = hashed_password
		db.session.commit()
		flash('Your password has been updated, now you can Signin', 'success')
		return redirect(url_for('signin'))
	return render_template('reset_token.html', title = "Reset Password", form = form)


# Custom error pages
@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html', title = "404")

@app.errorhandler(403)
def page_not_found(e):
	return render_template('403.html', title = "403")

@app.errorhandler(500)
def page_not_found(e):
	return render_template('500.html', title = "500")
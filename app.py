import os
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import psycopg2

# Initialize extensions
db = SQLAlchemy()

# Database models
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    files = db.relationship('File', backref='user', lazy=True, cascade="all, delete-orphan")

class File(db.Model):
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_type = db.Column(db.String(100))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    file_data = db.Column(db.LargeBinary)  # For storing files in DB
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

def create_app():
    app = Flask(__name__)
    
    # Configuration
    # app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://thd_user:1234@192.168.1.165:1201/thd_db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    
    # Initialize db with app
    db.init_app(app)
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip', 'rar', 'mp4', 'mp3', 'webp'}
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    def get_file_preview(file_data, filename):
        """Generate base64 preview for images"""
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
            return base64.b64encode(file_data).decode('utf-8')
        return None
    
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/upload', methods=['POST'])
    def upload_files():
        try:
            name = request.form.get('name', '').strip()
            if not name:
                return jsonify({'error': 'Имя обязательно для заполнения'}), 400
            
            files = request.files.getlist('files')
            if not files or files[0].filename == '':
                return jsonify({'error': 'Необходимо выбрать файлы для загрузки'}), 400
            
            # Create new user
            user = User(name=name)
            db.session.add(user)
            db.session.flush()
            
            uploaded_files = []
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{datetime.utcnow().timestamp()}_{filename}"
                    
                    file_data = file.read()
                    file_size = len(file_data)
                    file_type = file.content_type
                    
                    new_file = File(
                        filename=unique_filename,
                        original_filename=filename,
                        file_size=file_size,
                        file_type=file_type,
                        file_data=file_data,
                        user_id=user.id
                    )
                    
                    db.session.add(new_file)
                    uploaded_files.append({
                        'name': filename,
                        'size': file_size,
                        'type': file_type
                    })
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Успешно загружено {len(uploaded_files)} файлов для {name}',
                'user_id': user.id,
                'files': uploaded_files
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin')
    def admin_panel():
        return render_template('admin.html')
    
    @app.route('/api/files')
    def get_all_files():
        """API endpoint to get all files with user info"""
        users = User.query.order_by(User.upload_date.desc()).all()
        
        result = []
        for user in users:
            user_data = {
                'id': user.id,
                'name': user.name,
                'upload_date': user.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
                'files': []
            }
            
            for file in user.files:
                file_data = {
                    'id': file.id,
                    'filename': file.original_filename,
                    'size': file.file_size,
                    'type': file.file_type,
                    'upload_date': file.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'has_preview': file.file_type and file.file_type.startswith('image/')
                }
                
                # Generate preview for images
                if file.file_data and file.file_type and file.file_type.startswith('image/'):
                    file_data['preview'] = get_file_preview(file.file_data, file.original_filename)
                
                user_data['files'].append(file_data)
            
            result.append(user_data)
        
        return jsonify(result)
    
    @app.route('/api/file/<int:file_id>')
    def download_file(file_id):
        """Download or view file"""
        file = File.query.get_or_404(file_id)
        
        if file.file_data:
            from flask import send_file
            import io
            return send_file(
                io.BytesIO(file.file_data),
                mimetype=file.file_type or 'application/octet-stream',
                as_attachment=True,
                download_name=file.original_filename
            )
        
        return jsonify({'error': 'File not found'}), 404
    
    @app.route('/api/delete/<int:file_id>', methods=['DELETE'])
    def delete_file(file_id):
        """Delete a specific file"""
        try:
            file = File.query.get_or_404(file_id)
            user_id = file.user_id
            db.session.delete(file)
            db.session.commit()
            
            # Check if user has any files left
            remaining_files = File.query.filter_by(user_id=user_id).count()
            if remaining_files == 0:
                # Delete user if no files remain
                user = User.query.get(user_id)
                if user:
                    db.session.delete(user)
                    db.session.commit()
            
            return jsonify({'success': True, 'message': 'File deleted successfully'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/delete-user/<int:user_id>', methods=['DELETE'])
    def delete_user(user_id):
        """Delete user and all their files"""
        try:
            user = User.query.get_or_404(user_id)
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True, 'message': 'User and all files deleted successfully'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
    
    # Create tables and add file_data column if needed
    with app.app_context():
        db.create_all()
        # Ensure file_data column exists
        try:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE files ADD COLUMN IF NOT EXISTS file_data BYTEA'))
                conn.commit()
        except Exception as e:
            print(f"Note: {e}")
    
    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
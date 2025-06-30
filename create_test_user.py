from app import app, db, User

with app.app_context():
    # Check if test user already exists
    if not User.query.filter_by(username='test').first():
        user = User(
            username='test',
            email='test@example.com',
            is_active=True
        )
        user.set_password('test123')
        db.session.add(user)
        db.session.commit()
        print("Test user created successfully!")
    else:
        print("Test user already exists")

    # Create student user
    if not User.query.filter_by(username='student1').first():
        student = User(
            username='student1',
            email='student1@example.com',
            is_active=True
        )
        student.set_password('studentpass')
        db.session.add(student)
        db.session.commit()
        print("Student user created successfully!")
    else:
        print("Student user already exists")

    # Create teacher user
    if not User.query.filter_by(username='teacher1').first():
        teacher = User(
            username='teacher1',
            email='teacher1@example.com',
            is_active=True
        )
        teacher.set_password('teacherpass')
        db.session.add(teacher)
        db.session.commit()
        print("Teacher user created successfully!")
    else:
        print("Teacher user already exists")

    # Create admin user
    if not User.query.filter_by(username='admin1').first():
        admin = User(
            username='admin1',
            email='admin1@example.com',
            is_active=True
        )
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
    else:
        print("Admin user already exists")

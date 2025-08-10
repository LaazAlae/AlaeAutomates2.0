from flask import Blueprint, render_template

user_manual_bp = Blueprint('user_manual', __name__)

@user_manual_bp.route('/')
def user_manual():
    return render_template('user_manual/manual.html')
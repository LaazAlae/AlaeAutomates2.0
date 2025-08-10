from flask import Blueprint, render_template

help_bp = Blueprint('help', __name__)

@help_bp.route('/')
def help_page():
    return render_template('help/help.html')
from flask import Blueprint, render_template

cc_batch_bp = Blueprint('cc_batch', __name__)

@cc_batch_bp.route('/')
def cc_batch():
    return render_template('cc_batch/generator.html')
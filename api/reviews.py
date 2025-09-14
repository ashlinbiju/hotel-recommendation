from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user import User
from models.hotel import Hotel
from models.review import Review
from app import db
import logging
from datetime import datetime

reviews_bp = Blueprint('reviews', __name__)
logger = logging.getLogger(__name__)

@reviews_bp.route('/reviews/submit', methods=['POST'])
def submit_review():
    """Submit a new hotel review for collaborative filtering"""
    try:
        # Use default user ID for all reviews since authentication is optional
        user_id = 1  # Default user for anonymous reviews
        data = request.get_json()
        
        place_id = data.get('place_id')
        rating = data.get('rating')
        title = data.get('title', '')
        review_text = data.get('review_text', '')
        
        if not place_id or not rating:
            return jsonify({'error': 'Place ID and rating are required'}), 400
        
        if not (1 <= rating <= 5):
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Check if hotel exists in our database, if not create it
        hotel = Hotel.query.filter_by(place_id=place_id).first()
        if not hotel:
            # Create a new hotel record with minimal info
            hotel = Hotel(
                place_id=place_id,
                name=data.get('hotel_name', 'Hotel'),
                location='',
                rating=rating,
                total_reviews=1,
                is_active=True
            )
            db.session.add(hotel)
            db.session.flush()  # Get the hotel ID
        
        # Check if user already reviewed this hotel
        existing_review = Review.query.filter_by(
            user_id=user_id,
            hotel_id=hotel.id
        ).first()
        
        if existing_review:
            # Update existing review
            existing_review.rating = rating
            existing_review.comment = review_text
            existing_review.updated_at = datetime.utcnow()
            review = existing_review
        else:
            # Create new review
            review = Review(
                user_id=user_id,
                hotel_id=hotel.id,
                rating=rating,
                comment=review_text
            )
            db.session.add(review)
        
        # Update hotel rating statistics
        all_reviews = Review.query.filter_by(hotel_id=hotel.id).all()
        if all_reviews:
            avg_rating = sum(r.rating for r in all_reviews) / len(all_reviews)
            hotel.rating = round(avg_rating, 1)
            hotel.total_reviews = len(all_reviews)
        
        db.session.commit()
        
        logger.info(f"Review submitted by user {user_id} for hotel {place_id}")
        
        return jsonify({
            'message': 'Review submitted successfully',
            'review_id': review.id,
            'hotel_avg_rating': hotel.rating,
            'total_reviews': hotel.total_reviews
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting review: {str(e)}")
        return jsonify({'error': 'Failed to submit review'}), 500

@reviews_bp.route('/reviews/hotel/<place_id>', methods=['GET'])
def get_hotel_reviews(place_id):
    """Get all user reviews for a specific hotel"""
    try:
        hotel = Hotel.query.filter_by(place_id=place_id).first()
        if not hotel:
            return jsonify({'reviews': []}), 200
        
        reviews = db.session.query(Review, User).join(
            User, Review.user_id == User.id
        ).filter(Review.hotel_id == hotel.id).order_by(
            Review.created_at.desc()
        ).all()
        
        reviews_data = []
        for review, user in reviews:
            reviews_data.append({
                'id': review.id,
                'rating': review.rating,
                'title': review.title,
                'review_text': review.review_text,
                'username': user.username,
                'created_at': review.created_at.isoformat(),
                'user_id': review.user_id
            })
        
        return jsonify({'reviews': reviews_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting hotel reviews: {str(e)}")
        return jsonify({'error': 'Failed to get reviews'}), 500

@reviews_bp.route('/reviews/user/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_reviews(user_id):
    """Get all reviews by a specific user"""
    try:
        current_user_id = get_jwt_identity()
        
        # Users can only see their own reviews unless admin
        if current_user_id != user_id:
            user = User.query.get(current_user_id)
            if not user or not user.is_admin:
                return jsonify({'error': 'Unauthorized'}), 403
        
        reviews = db.session.query(Review, Hotel).join(
            Hotel, Review.hotel_id == Hotel.id
        ).filter(Review.user_id == user_id).order_by(
            Review.created_at.desc()
        ).all()
        
        reviews_data = []
        for review, hotel in reviews:
            reviews_data.append({
                'id': review.id,
                'rating': review.rating,
                'title': review.title,
                'review_text': review.review_text,
                'hotel_name': hotel.name,
                'hotel_place_id': hotel.place_id,
                'created_at': review.created_at.isoformat()
            })
        
        return jsonify({'reviews': reviews_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting user reviews: {str(e)}")
        return jsonify({'error': 'Failed to get user reviews'}), 500

@reviews_bp.route('/reviews/<int:review_id>', methods=['DELETE'])
@jwt_required()
def delete_review(review_id):
    """Delete a review (only by the author)"""
    try:
        user_id = get_jwt_identity()
        
        review = Review.query.get(review_id)
        if not review:
            return jsonify({'error': 'Review not found'}), 404
        
        if review.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        hotel = Hotel.query.get(review.hotel_id)
        
        db.session.delete(review)
        
        # Update hotel rating statistics
        if hotel:
            remaining_reviews = Review.query.filter_by(hotel_id=hotel.id).all()
            if remaining_reviews:
                avg_rating = sum(r.rating for r in remaining_reviews) / len(remaining_reviews)
                hotel.rating = round(avg_rating, 1)
                hotel.total_reviews = len(remaining_reviews)
            else:
                hotel.rating = 0
                hotel.total_reviews = 0
        
        db.session.commit()
        
        return jsonify({'message': 'Review deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting review: {str(e)}")
        return jsonify({'error': 'Failed to delete review'}), 500

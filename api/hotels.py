from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.hotel import Hotel
from models.review import Review
from models.user import User
from models.database import db
from services.api_service import get_google_place_details, get_google_place_photos
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

hotels_bp = Blueprint('hotels', __name__)

@hotels_bp.route('/hotels/<int:hotel_id>', methods=['GET'])
@jwt_required()
def get_hotel_details(hotel_id):
    """Get detailed information about a specific hotel"""
    try:
        logger.info(f"[DEBUG] Getting hotel details for ID: {hotel_id}")
        
        # Get hotel from database
        hotel = Hotel.query.get(hotel_id)
        if not hotel:
            logger.warning(f"[DEBUG] Hotel {hotel_id} not found in database")
            return jsonify({'error': 'Hotel not found'}), 404
        
        # Convert hotel to dictionary
        hotel_data = hotel.to_dict()
        
        # Get review count and average rating
        reviews = Review.query.filter_by(hotel_id=hotel_id).all()
        hotel_data['review_count'] = len(reviews)
        
        if reviews:
            hotel_data['rating'] = sum(r.rating for r in reviews) / len(reviews)
        else:
            hotel_data['rating'] = hotel.rating or 0.0
        
        # Try to get additional details from Google Places API if available
        if hotel.google_place_id:
            try:
                google_details = get_google_place_details(hotel.google_place_id)
                if google_details:
                    # Enhance hotel data with Google details
                    if 'formatted_phone_number' in google_details:
                        hotel_data['phone'] = google_details['formatted_phone_number']
                    if 'website' in google_details:
                        hotel_data['website'] = google_details['website']
                    if 'opening_hours' in google_details:
                        hotel_data['opening_hours'] = google_details['opening_hours']
                    if 'photos' in google_details:
                        hotel_data['photos'] = [photo['photo_reference'] for photo in google_details['photos'][:6]]
                    
                    logger.info(f"[DEBUG] Enhanced hotel data with Google Places details")
            except Exception as e:
                logger.error(f"[ERROR] Failed to get Google Places details: {e}")
        
        # Add fallback photos if none available
        if 'photos' not in hotel_data or not hotel_data['photos']:
            hotel_data['photos'] = [
                f"https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600&h=400&fit=crop",
                f"https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=600&h=400&fit=crop",
                f"https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?w=600&h=400&fit=crop"
            ]
        
        logger.info(f"[DEBUG] Successfully retrieved hotel details for {hotel.name}")
        return jsonify(hotel_data)
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to get hotel details: {e}")
        return jsonify({'error': 'Failed to retrieve hotel details'}), 500

@hotels_bp.route('/hotels/<int:hotel_id>/reviews', methods=['GET'])
@jwt_required()
def get_hotel_reviews(hotel_id):
    """Get reviews for a specific hotel"""
    try:
        logger.info(f"[DEBUG] Getting reviews for hotel ID: {hotel_id}")
        
        # Check if hotel exists
        hotel = Hotel.query.get(hotel_id)
        if not hotel:
            return jsonify({'error': 'Hotel not found'}), 404
        
        # Get reviews with user information
        reviews = db.session.query(Review, User).join(User, Review.user_id == User.id).filter(Review.hotel_id == hotel_id).order_by(Review.created_at.desc()).all()
        
        reviews_data = []
        for review, user in reviews:
            review_data = {
                'id': review.id,
                'rating': review.rating,
                'comment': review.comment,
                'review_text': review.comment,  # Alias for frontend compatibility
                'title': getattr(review, 'title', None),
                'user_name': user.username,
                'user_id': user.id,
                'created_at': review.created_at.isoformat() if review.created_at else None
            }
            reviews_data.append(review_data)
        
        logger.info(f"[DEBUG] Found {len(reviews_data)} reviews for hotel {hotel_id}")
        return jsonify(reviews_data)
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to get hotel reviews: {e}")
        return jsonify({'error': 'Failed to retrieve reviews'}), 500

@hotels_bp.route('/reviews', methods=['POST'])
@jwt_required()
def submit_review():
    """Submit a new review for a hotel"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        logger.info(f"[DEBUG] User {current_user_id} submitting review: {data}")
        
        # Validate required fields
        if not data or 'hotel_id' not in data or 'rating' not in data or 'review_text' not in data:
            return jsonify({'error': 'Missing required fields: hotel_id, rating, review_text'}), 400
        
        hotel_id = data['hotel_id']
        rating = data['rating']
        review_text = data['review_text']
        title = data.get('title', '')
        
        # Validate rating
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be an integer between 1 and 5'}), 400
        
        # Check if hotel exists
        hotel = Hotel.query.get(hotel_id)
        if not hotel:
            return jsonify({'error': 'Hotel not found'}), 404
        
        # Check if user already reviewed this hotel
        existing_review = Review.query.filter_by(user_id=current_user_id, hotel_id=hotel_id).first()
        if existing_review:
            # Update existing review
            existing_review.rating = rating
            existing_review.comment = review_text
            if hasattr(existing_review, 'title'):
                existing_review.title = title
            
            db.session.commit()
            logger.info(f"[DEBUG] Updated existing review for user {current_user_id}, hotel {hotel_id}")
            
            return jsonify({
                'message': 'Review updated successfully',
                'review_id': existing_review.id
            })
        else:
            # Create new review
            new_review = Review(
                user_id=current_user_id,
                hotel_id=hotel_id,
                rating=rating,
                comment=review_text
            )
            
            # Add title if the Review model supports it
            if hasattr(new_review, 'title'):
                new_review.title = title
            
            db.session.add(new_review)
            db.session.commit()
            
            logger.info(f"[DEBUG] Created new review for user {current_user_id}, hotel {hotel_id}")
            
            return jsonify({
                'message': 'Review submitted successfully',
                'review_id': new_review.id
            }), 201
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to submit review: {e}")
        db.session.rollback()
        return jsonify({'error': 'Failed to submit review'}), 500

@hotels_bp.route('/google/place-photos/<place_id>', methods=['GET'])
@jwt_required()
def get_place_photos(place_id):
    """Get photos for a Google Place"""
    try:
        logger.info(f"[DEBUG] Getting photos for Google Place ID: {place_id}")
        
        photos = get_google_place_photos(place_id)
        if photos:
            logger.info(f"[DEBUG] Found {len(photos)} photos for place {place_id}")
            return jsonify(photos)
        else:
            logger.warning(f"[DEBUG] No photos found for place {place_id}")
            return jsonify([])
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to get place photos: {e}")
        return jsonify([]), 500

@hotels_bp.route('/hotels', methods=['GET'])
@jwt_required()
def get_hotels():
    """Get list of hotels with optional filtering"""
    try:
        # Get query parameters
        location = request.args.get('location')
        min_rating = request.args.get('min_rating', type=float)
        max_price = request.args.get('max_price', type=float)
        limit = request.args.get('limit', 20, type=int)
        
        logger.info(f"[DEBUG] Getting hotels with filters: location={location}, min_rating={min_rating}, max_price={max_price}")
        
        # Build query
        query = Hotel.query.filter(Hotel.is_active == True)
        
        if location:
            query = query.filter(Hotel.location.ilike(f'%{location}%'))
        
        if min_rating:
            query = query.filter(Hotel.rating >= min_rating)
        
        if max_price:
            query = query.filter(Hotel.price_per_night <= max_price)
        
        hotels = query.limit(limit).all()
        
        # Convert to dictionaries and add review counts
        hotels_data = []
        for hotel in hotels:
            hotel_data = hotel.to_dict()
            
            # Get review count and average rating
            reviews = Review.query.filter_by(hotel_id=hotel.id).all()
            hotel_data['review_count'] = len(reviews)
            
            if reviews:
                hotel_data['rating'] = sum(r.rating for r in reviews) / len(reviews)
            
            hotels_data.append(hotel_data)
        
        logger.info(f"[DEBUG] Found {len(hotels_data)} hotels")
        return jsonify(hotels_data)
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to get hotels: {e}")
        return jsonify({'error': 'Failed to retrieve hotels'}), 500

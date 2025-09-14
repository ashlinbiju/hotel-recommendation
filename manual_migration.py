#!/usr/bin/env python3
"""
Manual migration script to add place_id field to hotels table
Run this if Flask migration commands are not working
"""

import sqlite3
import os

def add_place_id_column():
    """Add place_id column to hotels table manually"""
    
    # Database path
    db_path = os.path.join('instance', 'hotel_dev.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(hotels)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'place_id' in columns:
            print("place_id column already exists!")
            return True
        
        # Add the place_id column
        cursor.execute("""
            ALTER TABLE hotels 
            ADD COLUMN place_id VARCHAR(100)
        """)
        
        # Create index on place_id
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_hotels_place_id 
            ON hotels (place_id)
        """)
        
        # Commit changes
        conn.commit()
        print("✅ Successfully added place_id column to hotels table")
        print("✅ Created unique index on place_id")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🔄 Adding place_id column to hotels table...")
    success = add_place_id_column()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("You can now use the hotel details and review features.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")

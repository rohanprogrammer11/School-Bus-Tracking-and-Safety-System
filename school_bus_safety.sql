	-- ================================
	-- DATABASE
	-- ================================
	CREATE DATABASE IF NOT EXISTS school_bus_safety;
	USE school_bus_safety;

	-- ================================
	-- ORGANIZATION
	-- ================================
	CREATE TABLE organization (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_name VARCHAR(150) NOT NULL,
		address VARCHAR(255),
		email VARCHAR(150) UNIQUE,
		phone VARCHAR(20),
		password VARCHAR(255) NOT NULL,
		udise_code VARCHAR(20) UNIQUE,
		principal_name VARCHAR(100),
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
	);
    
    ALTER TABLE organization
		ADD COLUMN reset_token VARCHAR(255) NULL,
		ADD COLUMN reset_token_expiry DATETIME NULL;
        
	ALTER TABLE users
		ADD reset_token VARCHAR(255),
		ADD reset_expiry DATETIME;


	-- ================================
	-- USERS
	-- ================================
	CREATE TABLE users (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		name VARCHAR(100) NOT NULL,
		email VARCHAR(150) UNIQUE NOT NULL,
		phone VARCHAR(15),
		role ENUM('admin','driver','parent') NOT NULL,
		password_hash VARCHAR(255) NOT NULL,
		is_active BOOLEAN DEFAULT TRUE,
		last_login TIMESTAMP NULL,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);
    
    ALTER TABLE users
		ADD COLUMN otp_code VARCHAR(6) NULL,
		ADD COLUMN otp_expiry DATETIME NULL,
		ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;


	-- ================================
	-- DRIVER DETAILS
	-- ================================
	CREATE TABLE driver_details (
		driver_id INT PRIMARY KEY,
		driver_code VARCHAR(50) NOT NULL UNIQUE,
		license_number VARCHAR(50) NOT NULL UNIQUE,
		license_type VARCHAR(50),
		experience_years INT CHECK (experience_years >= 0),
		license_expiry DATE,
		blood_group VARCHAR(10),
		emergency_contact VARCHAR(20),
		status ENUM('ACTIVE','INACTIVE','SUSPENDED') DEFAULT 'ACTIVE',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
	);

ALTER TABLE driver_details
ADD COLUMN daily_salary DECIMAL(10,2) NOT NULL DEFAULT 0;

ALTER TABLE driver_details
CHANGE daily_salary monthly_salary DECIMAL(10,2) NOT NULL;

CREATE TABLE public_holidays (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id INT NOT NULL,
    holiday_date DATE NOT NULL,
    title VARCHAR(100),
    UNIQUE (org_id, holiday_date)
);

ALTER TABLE driver_details
ADD COLUMN overtime_rate DECIMAL(10,2) DEFAULT 0;

UPDATE driver_details
SET overtime_rate = 500
WHERE driver_id = 1;

ALTER TABLE driver_details
ADD COLUMN driver_full_name VARCHAR(100),
ADD COLUMN mobile_number VARCHAR(15);

ALTER TABLE driver_details
ADD COLUMN photo_path VARCHAR(255) NULL AFTER monthly_salary;


	-- ================================
	-- Driver Documents
	-- ================================

CREATE TABLE  driver_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id INT NOT NULL,
    driver_id INT NOT NULL,
    document_type ENUM('LICENSE','AADHAR','MEDICAL') NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
    FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uniq_driver_doc (driver_id, document_type)
);

	-- ================================
	-- BUSES
	-- ================================
	CREATE TABLE buses (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		bus_code VARCHAR(50) NOT NULL,
		bus_number VARCHAR(50) NOT NULL,
		bus_model VARCHAR(100),
		capacity INT CHECK (capacity > 0),
		status ENUM('ACTIVE','INACTIVE','MAINTENANCE') DEFAULT 'ACTIVE',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		UNIQUE (org_id, bus_code),
		UNIQUE (org_id, bus_number),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);
    
    ALTER TABLE buses
		ADD COLUMN fuel_type ENUM('DIESEL','PETROL','CNG') NOT NULL DEFAULT 'DIESEL',
		ADD COLUMN mileage_kmpl DECIMAL(5,2) NOT NULL COMMENT 'km per liter';


	-- ================================
	-- ROUTES
	-- ================================
	CREATE TABLE routes (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		route_code VARCHAR(50) NOT NULL,
		route_name VARCHAR(100) NOT NULL,
		start_point VARCHAR(100),
		end_point VARCHAR(100),
		start_time TIME,
		drop_time TIME,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		UNIQUE (org_id, route_code),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);
    
    ALTER TABLE routes
	ADD COLUMN total_km DECIMAL(8,2) DEFAULT 0 COMMENT 'Total route distance in KM';
    
    ALTER TABLE routes
	ADD COLUMN round_trip_km DECIMAL(8,2) DEFAULT 0
	COMMENT 'Pickup + Drop total distance';
    
UPDATE routes
SET round_trip_km = total_km * 2
WHERE id > 0;

    
-- ================================
-- DRIVER ASSIGNMENT (FINAL, SAFE)
-- ================================
CREATE TABLE driver_assignment (
    id INT AUTO_INCREMENT PRIMARY KEY,

    assignment_code VARCHAR(50) NOT NULL,

    org_id INT NOT NULL,
    driver_id INT NOT NULL,
    bus_id INT NOT NULL,
    route_id INT NOT NULL,

    assignment ENUM('PICKUP','DROP') NOT NULL,

    assignment_date DATE NOT NULL,
    assignment_time TIME DEFAULT NULL,

    repeat_type ENUM('NONE','DAILY','WEEKLY','MONTHLY') DEFAULT 'NONE',
    status ENUM('ASSIGNED','COMPLETED','CANCELLED') DEFAULT 'ASSIGNED',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    /* 🔐 ONE ROW PER DRIVER PER ASSIGNMENT */
    UNIQUE KEY uniq_driver_assignment (
        org_id,
        driver_id,
        assignment
    ),

    KEY idx_assignment_date (assignment_date),
    KEY idx_bus_id (bus_id),
    KEY idx_route_id (route_id),

    CONSTRAINT fk_da_org
        FOREIGN KEY (org_id)
        REFERENCES organization(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_da_driver
        FOREIGN KEY (driver_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_da_bus
        FOREIGN KEY (bus_id)
        REFERENCES buses(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_da_route
        FOREIGN KEY (route_id)
        REFERENCES routes(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4;

SET GLOBAL event_scheduler = ON;

#-----------------------------------
#----------------------------------
CREATE EVENT roll_driver_assignments_daily
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_DATE + INTERVAL 1 DAY
DO
UPDATE driver_assignment
SET assignment_date = CURDATE()
WHERE assignment_date < CURDATE();

#-----------------------------------
#----------------------------------
CREATE EVENT generate_next_day_assignments
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_DATE + INTERVAL 1 DAY
DO
INSERT INTO driver_assignment (
    assignment_code,
    org_id,
    driver_id,
    bus_id,
    route_id,
    assignment,
    assignment_date,
    assignment_time,
    repeat_type,
    status
)
SELECT
    CONCAT('AUTO-', DATE_FORMAT(CURDATE() + INTERVAL 1 DAY, '%Y%m%d'), '-', driver_id),
    org_id,
    driver_id,
    bus_id,
    route_id,
    assignment,
    CURDATE() + INTERVAL 1 DAY,
    assignment_time,
    repeat_type,
    'ASSIGNED'
FROM driver_assignment
WHERE
    assignment_date = CURDATE()
    AND repeat_type IN ('DAILY');




	-- ================================
	-- ROUTE STOPS
	-- ================================
	CREATE TABLE route_stop (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		route_id INT NOT NULL,
		stop_name VARCHAR(150) NOT NULL,
		latitude DOUBLE NOT NULL,
		longitude DOUBLE NOT NULL,
		stop_order INT NOT NULL,
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
	);
    
    ALTER TABLE route_stop
	ADD COLUMN monthly_fee DECIMAL(10,2) NOT NULL DEFAULT 0;



	-- ================================
	-- DRIVER ATTENDANCE
	-- ================================
	CREATE TABLE driver_attendance (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		driver_id INT NOT NULL,
		date DATE NOT NULL,
		check_in DATETIME,
		check_out DATETIME,
		status ENUM('PRESENT','ABSENT','LEAVE') DEFAULT 'ABSENT',
		UNIQUE (driver_id, date),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
	);

ALTER TABLE driver_attendance
MODIFY status ENUM('PRESENT','ABSENT','LEAVE','HOLIDAY','OVERTIME');


	-- ================================
	-- CLASS MASTER
	-- ================================
	CREATE TABLE class_master (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		std VARCHAR(20) NOT NULL,
		division VARCHAR(10),
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		UNIQUE (org_id, std, division),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);

	-- ================================
	-- STUDENT
	-- ================================
	CREATE TABLE student (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		name VARCHAR(100) NOT NULL,
		class_id INT NOT NULL,
		roll_no VARCHAR(50) NOT NULL,
		parent_id INT,
		rfid_tag VARCHAR(100),
		qr_code VARCHAR(100),
		assigned_stop_id INT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		UNIQUE (org_id, roll_no),
		UNIQUE (org_id, rfid_tag),
		UNIQUE (org_id, qr_code),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (class_id) REFERENCES class_master(id) ON DELETE CASCADE,
		FOREIGN KEY (parent_id) REFERENCES users(id) ON DELETE SET NULL,
		FOREIGN KEY (assigned_stop_id) REFERENCES route_stop(id) ON DELETE SET NULL
	);

	ALTER TABLE student
	ADD COLUMN bus_id INT NULL AFTER parent_id,
	ADD FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE SET NULL;
    
ALTER TABLE student
ADD UNIQUE KEY uniq_class_roll (org_id, class_id, roll_no);

    

    
    
    #--------------------
    # student bus fee
    #------------------------
    CREATE TABLE student_bus_fee (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    org_id INT NOT NULL,
    student_id INT NOT NULL,

    total_fee DECIMAL(10,2) NOT NULL,
    amount_paid DECIMAL(10,2) NOT NULL DEFAULT 0,

    billing_month DATE NOT NULL, -- e.g. 2026-02-01

    status ENUM('UNPAID','PARTIAL','PAID') DEFAULT 'UNPAID',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (student_id, billing_month),

    FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
);

#-----------------------
# 
#----------------------
CREATE TABLE student_fee_payment (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    fee_id BIGINT NOT NULL,
    paid_amount DECIMAL(10,2) NOT NULL,
    payment_mode ENUM('CASH','UPI','CARD','BANK') NOT NULL,
    paid_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (fee_id) REFERENCES student_bus_fee(id) ON DELETE CASCADE
);


	-- ================================
	-- STUDENT ATTENDANCE
	-- ================================
	CREATE TABLE attendance (
		id INT AUTO_INCREMENT PRIMARY KEY,
		student_id INT NOT NULL,
		route_id INT NOT NULL,
		pickup_time DATETIME,
		drop_time DATETIME,
		status ENUM('ABSENT','PICKED','DROPPED') DEFAULT 'ABSENT',
		date DATE NOT NULL,
		UNIQUE (student_id, date),
		FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
		FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
	);

	-- ================================
	-- PICKUP / DROP LOGS
	-- ================================
	CREATE TABLE pickup_logs (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		student_id INT NOT NULL,
		bus_id INT NOT NULL,
		driver_id INT NOT NULL,
		event_type ENUM('pickup','drop') NOT NULL,
		method ENUM('rfid','qr','manual') NOT NULL,
		latitude DOUBLE,
		longitude DOUBLE,
		event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
		FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
		FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
	);

	-- ================================
	-- REAL-TIME BUS LOCATION
	-- ================================
	CREATE TABLE location_update (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		bus_id INT NOT NULL,
		latitude DOUBLE NOT NULL,
		longitude DOUBLE NOT NULL,
		speed FLOAT,
		event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE
	);

	-- ================================
	-- EMERGENCY EVENTS
	-- ================================
	CREATE TABLE emergency_events (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		bus_id INT NOT NULL,
		driver_id INT NOT NULL,
		event_type ENUM('SOS','ACCIDENT','BREAKDOWN') NOT NULL,
		latitude DOUBLE,
		longitude DOUBLE,
		description VARCHAR(255),
		event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
		FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
		FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
	);

-- ================================
-- NOTIFICATIONS (FINAL VERSION)
-- ================================
CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    org_id INT NOT NULL,
    user_id INT NOT NULL,

    -- role of receiver
    role ENUM('admin','driver','parent') NOT NULL,

    title VARCHAR(200) NOT NULL,
    message VARCHAR(500) NOT NULL,

    -- delivery / read tracking
    status ENUM('sent','delivered','failed') DEFAULT 'sent',
    is_read TINYINT DEFAULT 0,

    -- optional reference (trip / student / bus / emergency)
    reference_type VARCHAR(50) NULL,
    reference_id BIGINT NULL,

    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- foreign keys
    CONSTRAINT fk_notification_org
        FOREIGN KEY (org_id)
        REFERENCES organization(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_notification_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4;

ALTER TABLE notifications ADD COLUMN latitude DOUBLE NULL, ADD COLUMN longitude DOUBLE NULL, ADD COLUMN accuracy DOUBLE NULL;

	CREATE TABLE parent_student (
		parent_id INT,
		student_id INT,
		PRIMARY KEY (parent_id, student_id),
		FOREIGN KEY (parent_id) REFERENCES users(id),
		FOREIGN KEY (student_id) REFERENCES student(id)
	);
    
ALTER TABLE parent_student
ADD CONSTRAINT fk_parent_student_parent
FOREIGN KEY (parent_id)
REFERENCES users(id)
ON DELETE CASCADE;

ALTER TABLE parent_student
ADD CONSTRAINT fk_parent_student_student
FOREIGN KEY (student_id)
REFERENCES student(id)
ON DELETE CASCADE;

	CREATE TABLE bus_trip (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		assignment_id INT,
		trip_date DATE,
		start_time DATETIME,
		end_time DATETIME,
		status ENUM('STARTED','COMPLETED','CANCELLED')
	);
    
ALTER TABLE bus_trip
ADD COLUMN bus_id INT NULL,
ADD COLUMN route_id INT NULL,
ADD COLUMN distance_km DECIMAL(8,2) DEFAULT 0;

ALTER TABLE bus_trip
ADD CONSTRAINT fk_bus_trip_bus
    FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,

ADD CONSTRAINT fk_bus_trip_route
    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE SET NULL;

	CREATE TABLE holidays (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		holiday_date DATE NOT NULL,
		title VARCHAR(150),
		UNIQUE (org_id, holiday_date),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);

CREATE INDEX idx_fuel_trip_date ON fuel_consumption (trip_date);
CREATE INDEX idx_fuel_bus ON fuel_consumption (bus_id);
CREATE INDEX idx_fuel_org_date ON fuel_consumption (org_id, trip_date);


	-- ================================
	-- INDEXES (PERFORMANCE)
	-- ================================
	CREATE INDEX idx_org_users ON users (org_id);
	CREATE INDEX idx_org_students ON student (org_id);
	CREATE INDEX idx_org_buses ON buses (org_id);
	CREATE INDEX idx_route_stop_order ON route_stop (route_id, stop_order);
	CREATE INDEX idx_bus_location ON location_update (bus_id, event_time);
	CREATE INDEX idx_student_pickup_logs ON pickup_logs (student_id, event_time);
	CREATE INDEX idx_attendance_date ON attendance (date);
	CREATE INDEX idx_driver_assignment_date ON driver_assignment (assignment_date);
	CREATE INDEX idx_student_parent ON student (parent_id);
	CREATE INDEX idx_emergency_time ON emergency_events (event_time);
    CREATE INDEX idx_user_notifications ON notifications (user_id, role, is_read, event_time);
    CREATE INDEX idx_org_notifications ON notifications (org_id, event_time);


SET GLOBAL event_scheduler = ON;

CREATE EVENT cleanup_old_pickup_logs
ON SCHEDULE EVERY 1 DAY
DO
DELETE FROM pickup_logs
WHERE event_time < DATE_SUB(CURDATE(), INTERVAL 6 MONTH);


CREATE EVENT cleanup_old_notifications
ON SCHEDULE EVERY 1 DAY
DO
DELETE FROM notifications
WHERE event_time < DATE_SUB(CURDATE(), INTERVAL 2 MONTH);

#Fuel Price
CREATE TABLE fuel_price (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id INT NOT NULL,
    fuel_type ENUM('DIESEL','PETROL','CNG') NOT NULL,
    price_per_unit DECIMAL(8,2) NOT NULL,
    effective_from DATE NOT NULL,

    UNIQUE (org_id, fuel_type, effective_from),
    FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
);

# Fuel Consumtion
CREATE TABLE fuel_consumption (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    org_id INT NOT NULL,
    bus_id INT NOT NULL,
    trip_id BIGINT NOT NULL,

    trip_date DATE NOT NULL,
    distance_km DECIMAL(8,2) NOT NULL,
    mileage_kmpl DECIMAL(5,2) NOT NULL,

    fuel_used DECIMAL(8,2) NOT NULL,
    fuel_price DECIMAL(8,2) NOT NULL,
    fuel_cost DECIMAL(10,2) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
    FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
    FOREIGN KEY (trip_id) REFERENCES bus_trip(id) ON DELETE CASCADE
);


# Daily bus report
CREATE TABLE daily_bus_operation_report (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    org_id INT NOT NULL,
    report_date DATE NOT NULL,

    bus_id INT NOT NULL,
    driver_id INT NOT NULL,
    route_id INT NOT NULL,

    assignment_type ENUM('PICKUP','DROP') NOT NULL,

    total_distance_km DECIMAL(8,2) DEFAULT 0,
    total_trips INT DEFAULT 0,

    fuel_used DECIMAL(8,2) DEFAULT 0,
    fuel_cost DECIMAL(10,2) DEFAULT 0,

    first_trip_start DATETIME NULL,
    last_trip_end DATETIME NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uniq_daily_bus (bus_id, driver_id, route_id, report_date),

    FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE,
    FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
    FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
);

# Run this once per day (midnight) or  generate_daily_bus_report
CREATE EVENT generate_daily_bus_report
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_DATE + INTERVAL 1 DAY
DO
INSERT INTO daily_bus_operation_report (
    org_id,
    report_date,
    bus_id,
    driver_id,
    route_id,
    assignment_type,
    total_distance_km,
    total_trips,
    fuel_used,
    fuel_cost,
    first_trip_start,
    last_trip_end
)
SELECT
    b.org_id,
    bt.trip_date,
    bt.bus_id,
    da.driver_id,
    da.route_id,
    da.assignment,

    SUM(bt.distance_km),
    COUNT(bt.id),

    SUM(fc.fuel_used),
    SUM(fc.fuel_cost),

    MIN(bt.start_time),
    MAX(bt.end_time)

FROM bus_trip bt
JOIN driver_assignment da ON da.id = bt.assignment_id
JOIN buses b ON b.id = bt.bus_id
LEFT JOIN fuel_consumption fc ON fc.trip_id = bt.id

WHERE bt.trip_date = CURDATE() - INTERVAL 1 DAY

GROUP BY
    bt.trip_date,
    bt.bus_id,
    da.driver_id,
    da.route_id,
    da.assignment;


DROP EVENT IF EXISTS roll_driver_assignments_daily;


ALTER TABLE driver_assignment
ADD UNIQUE KEY uniq_driver_assignment_date (
    org_id,
    driver_id,
    assignment,
    assignment_date
);


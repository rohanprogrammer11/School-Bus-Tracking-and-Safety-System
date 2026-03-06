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

CREATE EVENT roll_driver_assignments_daily
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_DATE + INTERVAL 1 DAY
DO
UPDATE driver_assignment
SET assignment_date = CURDATE()
WHERE assignment_date < CURDATE();



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

	CREATE TABLE bus_trip (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		assignment_id INT,
		trip_date DATE,
		start_time DATETIME,
		end_time DATETIME,
		status ENUM('STARTED','COMPLETED','CANCELLED')
	);

	CREATE TABLE holidays (
		id INT AUTO_INCREMENT PRIMARY KEY,
		org_id INT NOT NULL,
		holiday_date DATE NOT NULL,
		title VARCHAR(150),
		UNIQUE (org_id, holiday_date),
		FOREIGN KEY (org_id) REFERENCES organization(id) ON DELETE CASCADE
	);



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



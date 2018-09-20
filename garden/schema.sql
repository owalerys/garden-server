DROP TABLE IF EXISTS client;
DROP TABLE IF EXISTS slave;
DROP TABLE IF EXISTS sensor;
DROP TABLE IF EXISTS relay;
DROP TABLE IF EXISTS schedule;
DROP TABLE IF EXISTS rule;
DROP TABLE IF EXISTS element;
DROP TABLE IF EXISTS consequence;
DROP TABLE IF EXISTS rule_limit;
DROP TABLE IF EXISTS activation;
DROP TABLE IF EXISTS measurement;

CREATE TABLE client (
  uuid VARCHAR(36) PRIMARY KEY,
  identifier VARCHAR(255) UNIQUE NOT NULL,
  secret VARCHAR(255) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT 0,
  nickname VARCHAR(255) NOT NULL
);

CREATE INDEX client_identifier ON client (identifier);

CREATE TABLE slave (
  uuid VARCHAR(36) PRIMARY KEY,
  nickname VARCHAR(255) NULL,
  connected BOOLEAN NOT NULL DEFAULT 0,
  last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sensor (
  uuid VARCHAR(36) PRIMARY KEY,
  nickname VARCHAR(255) NULL,
  slave_uuid VARCHAR(36) NOT NULL,
  digital BOOLEAN NOT NULL DEFAULT 1,
  driver VARCHAR(255) NOT NULL,
  pin TINYINT NOT NULL DEFAULT 0,
  measurement_type VARCHAR(255) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT 1,
  FOREIGN KEY (slave_uuid) REFERENCES slave (uuid)
);

CREATE TABLE relay (
  uuid VARCHAR(36) PRIMARY KEY,
  nickname VARCHAR(255) NULL,
  slave_uuid VARCHAR(36) NOT NULL,
  relay_type VARCHAR(255) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT 1,
  manual BOOLEAN NOT NULL DEFAULT 0,
  FOREIGN KEY (slave_uuid) REFERENCES slave (uuid)
);

CREATE TABLE schedule (
  uuid VARCHAR(36) PRIMARY KEY,
  nickname VARCHAR(255) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE rule(
  uuid VARCHAR(36) PRIMARY KEY,
  nickname VARCHAR(255) NULL,
  schedule_uuid VARCHAR(36) NOT NULL,
  logic_type VARCHAR(20) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT 1,
  FOREIGN KEY (schedule_uuid) REFERENCES schedule (uuid)
);

CREATE TABLE element(
  uuid VARCHAR(36) PRIMARY KEY,
  rule_uuid VARCHAR(36) NOT NULL,
  sensor_uuid VARCHAR(36) NOT NULL,
  max_value DECIMAL(10,5) NULL,
  min_value DECIMAL(10,5) NULL,
  FOREIGN KEY (rule_uuid) REFERENCES rule (uuid)
  FOREIGN KEY (sensor_uuid) REFERENCES sensor (uuid)
);

CREATE TABLE consequence(
  uuid VARCHAR(36) PRIMARY KEY,
  rule_uuid VARCHAR(36) NOT NULL,
  relay_uuid VARCHAR(36) NOT NULL,
  FOREIGN KEY (rule_uuid) REFERENCES rule (uuid),
  FOREIGN KEY (relay_uuid) REFERENCES relay (uuid)
);

CREATE TABLE rule_limit(
  uuid VARCHAR(36) PRIMARY KEY,
  rule_uuid VARCHAR(36) NOT NULL,
  period INTEGER NOT NULL,
  every INTEGER NOT NULL,
  FOREIGN KEY (rule_uuid) REFERENCES rule (uuid)
);

CREATE TABLE activation(
  uuid VARCHAR(36) PRIMARY KEY,
  rule_uuid VARCHAR(36) NULL,
  relay_uuid VARCHAR(36) NULL,
  start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  end_time TIMESTAMP NULL,
  last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_uuid) REFERENCES rule (uuid),
  FOREIGN KEY (relay_uuid) REFERENCES relay (uuid)
);

CREATE INDEX activation_time ON activation (end_time, start_time);

CREATE TABLE measurement(
  uuid VARCHAR(36) PRIMARY KEY,
  sensor_uuid VARCHAR(36) NOT NULL,
  recorded_value DECIMAL(10,5) NULL,
  recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (sensor_uuid) REFERENCES sensor (uuid)
);

CREATE INDEX measurement_recorded_at ON measurement (recorded_at);

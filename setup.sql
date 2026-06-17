CREATE DATABASE expense_db;
CREATE USER 'expense_user'@'%' IDENTIFIED BY 'StrongPassword123';
GRANT ALL PRIVILEGES ON expense_db.* TO 'expense_user'@'%';
FLUSH PRIVILEGES;

CREATE TABLE expense (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(100),
  amount DECIMAL(10,2),
  category VARCHAR(50),
  date DATE
);

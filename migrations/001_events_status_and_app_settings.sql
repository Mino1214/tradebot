-- 프로젝트와 기존 MariaDB 스키마 병합용
-- 이미 만든 events, candles, param_sets, signals, orders, positions 는 그대로 두고
-- 아래만 실행하면 됨.

SET NAMES utf8mb4;

-- 1) events 테이블에 status 컬럼 추가 (워커가 pending/processed 구분용)
-- (이미 있으면 에러 나므로 한 번만 실행)
ALTER TABLE events
  ADD COLUMN status VARCHAR(16) DEFAULT 'pending' AFTER raw;

-- 2) positions 테이블에 고정 스탑가 컬럼 (한 번만 실행, 이미 있으면 에러 무시)
ALTER TABLE positions ADD COLUMN stopPrice DECIMAL(20,8) NULL AFTER entryPrice;

-- 3) 킬스위치(trade_enabled) 등 앱 설정용 테이블
CREATE TABLE IF NOT EXISTS app_settings (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `key` VARCHAR(64) NOT NULL,
  value VARCHAR(256) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_app_settings_key (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

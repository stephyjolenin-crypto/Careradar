create table hospitals (
  id bigint generated always as identity primary key,
  name text not null,
  lat double precision not null,
  lng double precision not null,
  phone text,
  specialties text[] default '{}',
  has_ct boolean default false,
  has_trauma boolean default false,
  icu_free int default 0,
  beds_free int default 0,
  ventilators_free int default 0,
  oxygen boolean default true,
  blood_groups text[] default '{}',
  updated_at timestamptz default now()
);

create table alerts (
  id bigint generated always as identity primary key,
  hospital_id bigint references hospitals(id),
  emergency_type text,
  eta_min int,
  created_at timestamptz default now()
);

create or replace function touch_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;

create trigger hospitals_touch before update on hospitals
for each row execute function touch_updated_at();

insert into hospitals (name, lat, lng, specialties, has_ct, has_trauma, icu_free, beds_free, ventilators_free, oxygen, blood_groups) values
('Chettinad Health City', 12.7957, 80.2231, '{cardiac,stroke,accident,pregnancy}', true, true, 4, 22, 3, true, '{A+,B+,O+,AB+}'),
('Apollo Speciality OMR', 12.9066, 80.2299, '{cardiac,accident,pregnancy}', true, false, 2, 9, 1, true, '{A+,O+,O-}'),
('MIOT International', 13.0226, 80.1851, '{cardiac,stroke,accident}', true, true, 1, 12, 2, true, '{B+,O+}'),
('Fortis Malar Adyar', 13.0067, 80.2570, '{cardiac,stroke,pregnancy}', true, false, 5, 14, 4, true, '{A+,B+,AB+}'),
('Government General Hospital', 13.0827, 80.2785, '{cardiac,stroke,accident,pregnancy}', true, true, 1, 30, 2, true, '{O+,O-,B+}'),
('Sri Ramachandra Medical Centre', 13.0356, 80.1459, '{cardiac,stroke,accident,pregnancy}', true, true, 3, 18, 3, true, '{A+,O+,AB-}');

alter publication supabase_realtime add table hospitals, alerts;

alter table hospitals enable row level security;
alter table alerts enable row level security;

create policy "read hospitals" on hospitals for select using (true);
create policy "update hospitals" on hospitals for update using (true) with check (true);
create policy "read alerts" on alerts for select using (true);
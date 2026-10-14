--
-- PostgreSQL database dump
--

\restrict Yw847bfASWRm9Jf60CabivbHrIB3n4MM7kAypvlJYothCzrWzCEsKFntnIySoO4

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, name, email, password_hash, created_at) FROM stdin;
00000000-0000-0000-0000-000000000001	Usuário Temporário	temp@snowmap.com	hash_de_teste_temporario	2026-07-28 15:58:54.434235
\.


--
-- PostgreSQL database dump complete
--

\unrestrict Yw847bfASWRm9Jf60CabivbHrIB3n4MM7kAypvlJYothCzrWzCEsKFntnIySoO4


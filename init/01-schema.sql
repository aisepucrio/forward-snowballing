--
-- PostgreSQL database dump
--

\restrict jExfm7pBEuwLdcNzwFbTZGanWLmCnpW96D0o9mmO1XoaWEBDajDaKJPAz3HFQMM

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
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: criteria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.criteria (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    search_id uuid NOT NULL,
    description text NOT NULL,
    type character varying(20) NOT NULL,
    CONSTRAINT criteria_type_check CHECK (((type)::text = ANY ((ARRAY['inclusion'::character varying, 'exclusion'::character varying])::text[])))
);


--
-- Name: criteria_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.criteria_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    paper_id uuid NOT NULL,
    criteria_id uuid NOT NULL,
    passed boolean NOT NULL,
    reason text,
    evaluated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: paper_authors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paper_authors (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    paper_id uuid NOT NULL,
    name text NOT NULL,
    author_order integer NOT NULL
);


--
-- Name: papers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.papers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    venue_id uuid,
    doi character varying(255),
    semantic_paper_id character varying(255),
    openalex_id character varying(255),
    title text NOT NULL,
    year integer,
    abstract text,
    citation_count integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: search_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    search_id uuid NOT NULL,
    paper_id uuid NOT NULL,
    selected_first_page boolean DEFAULT false NOT NULL,
    excluded_duplicate boolean DEFAULT false NOT NULL,
    duplicate_of uuid,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: searches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.searches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    seed_paper_id uuid NOT NULL,
    created_by uuid NOT NULL,
    direction character varying(20) NOT NULL,
    data_source character varying(50),
    executed_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT searches_direction_check CHECK (((direction)::text = ANY ((ARRAY['forward'::character varying, 'backward'::character varying])::text[])))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: venues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.venues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    type character varying(20) NOT NULL,
    qualis character varying(5),
    impact_factor double precision,
    h_index integer,
    source text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT venues_type_check CHECK (((type)::text = ANY ((ARRAY['journal'::character varying, 'conference'::character varying])::text[])))
);


--
-- Name: criteria_logs criteria_logs_paper_id_criteria_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria_logs
    ADD CONSTRAINT criteria_logs_paper_id_criteria_id_key UNIQUE (paper_id, criteria_id);


--
-- Name: criteria_logs criteria_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria_logs
    ADD CONSTRAINT criteria_logs_pkey PRIMARY KEY (id);


--
-- Name: criteria criteria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria
    ADD CONSTRAINT criteria_pkey PRIMARY KEY (id);


--
-- Name: paper_authors paper_authors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_authors
    ADD CONSTRAINT paper_authors_pkey PRIMARY KEY (id);


--
-- Name: papers papers_doi_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.papers
    ADD CONSTRAINT papers_doi_key UNIQUE (doi);


--
-- Name: papers papers_openalex_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.papers
    ADD CONSTRAINT papers_openalex_id_key UNIQUE (openalex_id);


--
-- Name: papers papers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.papers
    ADD CONSTRAINT papers_pkey PRIMARY KEY (id);


--
-- Name: papers papers_semantic_paper_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.papers
    ADD CONSTRAINT papers_semantic_paper_id_key UNIQUE (semantic_paper_id);


--
-- Name: search_results search_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_results
    ADD CONSTRAINT search_results_pkey PRIMARY KEY (id);


--
-- Name: search_results search_results_search_id_paper_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_results
    ADD CONSTRAINT search_results_search_id_paper_id_key UNIQUE (search_id, paper_id);


--
-- Name: searches searches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.searches
    ADD CONSTRAINT searches_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: venues venues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.venues
    ADD CONSTRAINT venues_pkey PRIMARY KEY (id);


--
-- Name: idx_criteria_logs_criteria; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_criteria_logs_criteria ON public.criteria_logs USING btree (criteria_id);


--
-- Name: idx_criteria_logs_paper; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_criteria_logs_paper ON public.criteria_logs USING btree (paper_id);


--
-- Name: idx_criteria_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_criteria_search ON public.criteria USING btree (search_id);


--
-- Name: idx_paper_authors_paper; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_paper_authors_paper ON public.paper_authors USING btree (paper_id);


--
-- Name: idx_papers_doi; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_papers_doi ON public.papers USING btree (doi);


--
-- Name: idx_papers_openalex; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_papers_openalex ON public.papers USING btree (openalex_id);


--
-- Name: idx_papers_semantic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_papers_semantic ON public.papers USING btree (semantic_paper_id);


--
-- Name: idx_papers_venue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_papers_venue ON public.papers USING btree (venue_id);


--
-- Name: idx_search_results_excluded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_results_excluded ON public.search_results USING btree (excluded_duplicate);


--
-- Name: idx_search_results_paper; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_results_paper ON public.search_results USING btree (paper_id);


--
-- Name: idx_search_results_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_results_search ON public.search_results USING btree (search_id);


--
-- Name: idx_search_results_selected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_results_selected ON public.search_results USING btree (selected_first_page);


--
-- Name: idx_searches_seed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_searches_seed ON public.searches USING btree (seed_paper_id);


--
-- Name: idx_searches_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_searches_user ON public.searches USING btree (created_by);


--
-- Name: criteria_logs criteria_logs_criteria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria_logs
    ADD CONSTRAINT criteria_logs_criteria_id_fkey FOREIGN KEY (criteria_id) REFERENCES public.criteria(id) ON DELETE CASCADE;


--
-- Name: criteria_logs criteria_logs_paper_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria_logs
    ADD CONSTRAINT criteria_logs_paper_id_fkey FOREIGN KEY (paper_id) REFERENCES public.papers(id) ON DELETE CASCADE;


--
-- Name: criteria criteria_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.criteria
    ADD CONSTRAINT criteria_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON DELETE CASCADE;


--
-- Name: paper_authors paper_authors_paper_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_authors
    ADD CONSTRAINT paper_authors_paper_id_fkey FOREIGN KEY (paper_id) REFERENCES public.papers(id) ON DELETE CASCADE;


--
-- Name: papers papers_venue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.papers
    ADD CONSTRAINT papers_venue_id_fkey FOREIGN KEY (venue_id) REFERENCES public.venues(id) ON DELETE SET NULL;


--
-- Name: search_results search_results_duplicate_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_results
    ADD CONSTRAINT search_results_duplicate_of_fkey FOREIGN KEY (duplicate_of) REFERENCES public.papers(id);


--
-- Name: search_results search_results_paper_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_results
    ADD CONSTRAINT search_results_paper_id_fkey FOREIGN KEY (paper_id) REFERENCES public.papers(id) ON DELETE CASCADE;


--
-- Name: search_results search_results_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_results
    ADD CONSTRAINT search_results_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON DELETE CASCADE;


--
-- Name: searches searches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.searches
    ADD CONSTRAINT searches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: searches searches_seed_paper_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.searches
    ADD CONSTRAINT searches_seed_paper_id_fkey FOREIGN KEY (seed_paper_id) REFERENCES public.papers(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict jExfm7pBEuwLdcNzwFbTZGanWLmCnpW96D0o9mmO1XoaWEBDajDaKJPAz3HFQMM


from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.base import Base

class StructuredTable(Base):
    __tablename__ = 'structured_tables'
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey('parsed_sections.id', ondelete='CASCADE'), nullable=False)
    page_num = Column(Integer, nullable=False)
    order_index = Column(Integer, nullable=False)
    row_count = Column(Integer, default=0)
    col_count = Column(Integer, default=0)
    status = Column(String, default="pending_review")
    bbox = Column(String, nullable=True) # format: x0,y0,x1,y1

    rows = relationship("StructuredRow", back_populates="table", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint('section_id', 'order_index', name='uq_structured_table_order'),
    )

class StructuredRow(Base):
    __tablename__ = 'structured_rows'
    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey('structured_tables.id', ondelete='CASCADE'), nullable=False)
    row_index = Column(Integer, nullable=False)
    is_header = Column(Boolean, default=False)

    cells = relationship("StructuredCell", back_populates="row", cascade="all, delete-orphan", passive_deletes=True)

    table = relationship("StructuredTable", back_populates="rows")

    __table_args__ = (
        UniqueConstraint('table_id', 'row_index', name='uq_structured_row_index'),
    )

class StructuredCell(Base):
    __tablename__ = 'structured_cells'
    id = Column(Integer, primary_key=True, index=True)
    row_id = Column(Integer, ForeignKey('structured_rows.id', ondelete='CASCADE'), nullable=False)
    col_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    original_content = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    is_modified = Column(Boolean, default=False)
    col_span = Column(Integer, default=1)
    row_span = Column(Integer, default=1)

    row = relationship("StructuredRow", back_populates="cells")

    __table_args__ = (
        UniqueConstraint('row_id', 'col_index', name='uq_structured_cell_index'),
    )

import streamlit as st
import psycopg2 as pg
from datetime import date
import pandas as pd
import os
from io import BytesIO
from utils import compute_aging_bucket


def main():
    # Database connection
    try:
        connection = pg.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASS'],
        port=os.environ.get('DB_PORT', 5432)
)
        cursor = connection.cursor()
        db_connected = True
    except Exception as e:
        st.warning("⚠️ Could not connect to Postgres. Running in demo mode with sample data.")
        db_connected = False

    
    # Sidebar filters
    st.sidebar.title('Invoice Dashboard')

    cursor.execute('SELECT name FROM customers ORDER BY name')
    customers_list = [row[0] for row in cursor.fetchall()]
    customer = st.sidebar.selectbox('Customer', ['All'] + customers_list)

    cursor.execute('SELECT min(invoice_date), max(invoice_date) FROM invoices')
    start_date_db, end_date_db = cursor.fetchone()
    start_date = st.sidebar.date_input('Start date', value=start_date_db, min_value=start_date_db, max_value=end_date_db)
    end_date = st.sidebar.date_input('End date', value=end_date_db, min_value=start_date_db, max_value=end_date_db)

    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    query = """ 
        SELECT 
            c.name AS customer_name,
            i.invoice_id,
            i.amount AS invoice_amount,
            COALESCE(SUM(p.amount), 0) AS payment_amount,
            i.amount - COALESCE(SUM(p.amount), 0) AS outstanding,
            i.invoice_date,
            i.due_date
        FROM invoices i
        JOIN customers c ON i.customer_id = c.customer_id
        LEFT JOIN payments p ON i.invoice_id = p.invoice_id
        GROUP BY i.invoice_id, c.name, i.amount, i.invoice_date, i.due_date
        ORDER BY i.invoice_id;
    """
    if db_connected:
        invoice_df = pd.read_sql(query, connection)
    else:
        invoice_df = pd.DataFrame({
            "customer_name": ["Alice", "Bob"],
            "invoice_id": [1, 2],
            "invoice_amount": [1000, 500],
            "payment_amount": [200, 500],
            "outstanding": [800, 0],
            "invoice_date": pd.to_datetime(["2025-01-01", "2025-02-01"]),
            "due_date": pd.to_datetime(["2025-01-15", "2025-02-15"])
        })

    invoice_df['invoice_amount'] = invoice_df['invoice_amount'].astype(int)
    invoice_df['payment_amount'] = invoice_df['payment_amount'].astype(int)
    invoice_df['outstanding'] = invoice_df['outstanding'].astype(int)
    invoice_df['invoice_date'] = pd.to_datetime(invoice_df['invoice_date'])
    invoice_df['due_date'] = pd.to_datetime(invoice_df['due_date'])


    # Apply filters
    if customer != 'All':
        invoice_df = invoice_df[invoice_df['customer_name'] == customer]

    invoice_df = invoice_df[(invoice_df['invoice_date'] >= start_date) & (invoice_df['invoice_date'] <= end_date)]

    total_invoices = invoice_df['invoice_amount'].sum()
    total_received = invoice_df['payment_amount'].sum()
    outstanding = total_invoices - total_received

    today_date = pd.to_datetime(date.today())
    overdue_df = invoice_df[invoice_df['due_date'] < today_date]
    overdue_amount = (overdue_df['invoice_amount'] - overdue_df['payment_amount']).sum()
    overdue_percentage = (overdue_amount / outstanding * 100) if outstanding > 0 else 0

    # Main dashboard
    # KPI cards
    col1, col2, col3, col4 = st.columns(4)

    def format_number(num):
        return f"{int(num):,}" if num == int(num) else f"{num:,.2f}"
    with col1:
        st.metric('Total Invoice', format_number(total_invoices))
    with col2:
        st.metric('Total Received', format_number(total_received))
    with col3:
        st.metric('Outstanding', format_number(outstanding))
    with col4:
        st.metric('Overdue', f'{overdue_percentage:.0f}%')
        st.caption(f"Overdue Amount: {format_number(overdue_amount)}")

    st.write("### Invoice Table")

    def highlight_overdue(row):
        return ['background-color: #ffcccc']*len(row) if row['due_date'] < pd.to_datetime(date.today()) and row['outstanding'] > 0 else ['']*len(row)

    search_text = st.sidebar.text_input("Search Invoice or Customer")
    display_df = invoice_df.copy()

    if search_text:
        display_df = display_df[
            display_df['customer_name'].str.contains(search_text, case=False) |
            display_df['invoice_id'].astype(str).str.contains(search_text)
        ]

    # Display invoice table
    display_df['aging_bucket'] = display_df.apply(
        lambda r: compute_aging_bucket(r['due_date'], today_date, r['outstanding']),
        axis=1
    )
    st.caption("Highlighted rows are overdue, Aging Bucket shows how long overdue.")
    st.dataframe(display_df.reset_index(drop=True).style.apply(highlight_overdue, axis=1))

    # Download button
    output = BytesIO()
    display_df.to_excel(output, index=False)
    st.download_button(
        "📥 Download Filtered Data",
        data=output.getvalue(),
        file_name="invoices.xlsx",
        mime="application/vnd.ms-excel"
    )

    # Payment recording
    display_cols = ['invoice_id', 'customer_name', 'invoice_amount', 'payment_amount', 'outstanding', 'invoice_date', 'due_date']
    with st.expander("📊 View Full Table (All Columns)"):
        st.dataframe(display_df[display_cols], height=400)

    with st.expander("💰 Record / View Payments"):
        invoice_options = {
            f"Invoice {row['invoice_id']} | {row['customer_name']} | Outstanding: {row['outstanding']:.2f}": row['invoice_id']
            for _, row in display_df.iterrows()
        }

        if 'selected_invoice' not in st.session_state or st.session_state.selected_invoice not in display_df['invoice_id'].values:
            st.session_state.selected_invoice = display_df['invoice_id'].iloc[0]

        selected_label = st.selectbox(
            "Select Invoice",
            options=list(invoice_options.keys()),
            index=list(invoice_options.values()).index(st.session_state.selected_invoice)
        )
        st.session_state.selected_invoice = invoice_options[selected_label]
        selected_invoice = st.session_state.selected_invoice

        invoice_row = display_df[display_df['invoice_id'] == selected_invoice].iloc[0]
        st.info(f"""
    **Invoice ID:** {invoice_row['invoice_id']}  
    **Customer:** {invoice_row['customer_name']}  
    **Invoice Amount:** {invoice_row['invoice_amount']:.2f}  
    **Already Paid:** {invoice_row['payment_amount']:.2f}  
    **Outstanding:** {invoice_row['outstanding']:.2f}  
    """)

        outstanding_amt = max(float(invoice_row['outstanding']), 0.0)
        with st.form("payment_form", clear_on_submit=True):
            payment_date = st.date_input("Payment Date", value=date.today())
            payment_amount = st.number_input(
                "Payment Amount",
                min_value=0.0,
                max_value=outstanding_amt,
                step=0.01
            )
            submitted = st.form_submit_button("💾 Record Payment")
            # Handle form submission
            if submitted:
                if payment_amount <= 0:
                    st.error("Payment must be > 0")
                elif payment_amount > outstanding_amt:
                    st.error("Cannot exceed outstanding")
                else:
                    cursor.execute(
                        "INSERT INTO payments (invoice_id, payment_date, amount) VALUES (%s, %s, %s)",
                        (selected_invoice, payment_date, payment_amount)
                    )
                    connection.commit()
                    st.success(f"✅ Payment of {payment_amount:.2f} recorded for Invoice {selected_invoice}.")
                    st.rerun()

        payment_df = pd.read_sql(
            "SELECT payment_id, payment_date, amount FROM payments WHERE invoice_id=%s ORDER BY payment_date",
            connection, params=(selected_invoice,)
        )
        if not payment_df.empty:
            st.write("### Payment Records for this Invoice")
            st.dataframe(payment_df.reset_index(drop=True))
        else:
            st.info("No payments recorded yet for this invoice.")

    # Overdue Analysis Chart
    query = """ 
        SELECT 
            c.name AS customer_name,
            i.invoice_id,
            i.amount AS invoice_amount,
            COALESCE(SUM(p.amount), 0) AS payment_amount,
            i.amount - COALESCE(SUM(p.amount), 0) AS outstanding,
            i.invoice_date,
            i.due_date
        FROM invoices i
        JOIN customers c ON i.customer_id = c.customer_id
        LEFT JOIN payments p ON i.invoice_id = p.invoice_id
        GROUP BY i.invoice_id, c.name, i.amount, i.invoice_date, i.due_date
        ORDER BY i.invoice_id;
    """
    raw_df = pd.read_sql(query, connection)
    invoice_df = raw_df.copy()

    raw_df['due_date_only'] = raw_df['due_date'].dt.date
    today = date.today()

    overdue_all_df = raw_df[raw_df['due_date_only'] < today]
    overdue_cust = overdue_all_df.groupby('customer_name', as_index=False)['outstanding'].sum()
    top5 = overdue_cust.sort_values('outstanding', ascending=False).head(5)

    if not top5.empty:
        import altair as alt
        chart = alt.Chart(top5).mark_bar(color='#ff6666').encode(
            x=alt.X('customer_name', sort='-y', title='Customer'),
            y=alt.Y('outstanding', title='Outstanding Amount'),
            tooltip=['customer_name', 'outstanding']
        ).properties(
            height=400,
            width=600,
            title='Top 5 Customers by Overdue Outstanding (All Customers)'
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No overdue outstanding amounts to display.")

if __name__ == '__main__':
    main()

